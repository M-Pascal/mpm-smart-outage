"""Mirror MicroPowerManager's mini-grids, cities (service areas), customers and meters into PowerChat.

MPM remains the source of truth: only MPM-owned fields (names, phone, area, meters) are overwritten.
PowerChat-owned fields (WhatsApp consent, notification preference) are never touched by a sync, and new
MPM customers start without WhatsApp consent until an operator records it.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import now as clock_now
from ..db import WRITE_LOCK
from ..integrations.mpm import MpmClient
from ..models import Customer, Meter, MiniGrid, ServiceArea
from ..phone import normalize
from . import activity

log = logging.getLogger("powerchat.mpm_sync")


def _primary_address(person: dict) -> dict | None:
    addresses = person.get("addresses") or []
    return next((a for a in addresses if int(a.get("is_primary") or 0) == 1), addresses[0] if addresses else None)


def _person_name(person: dict) -> str:
    return " ".join(p for p in (person.get("name"), person.get("surname")) if p).strip() or f"MPM person {person['id']}"


def sync(db: Session, client: MpmClient) -> dict[str, Any]:
    with WRITE_LOCK:
        return _sync(db, client)


def _sync(db: Session, client: MpmClient) -> dict[str, Any]:
    t = clock_now()
    summary = {"mini_grids": 0, "service_areas": 0, "customers_created": 0, "customers_updated": 0,
               "customers_deactivated": 0, "meters": 0, "skipped": {}}

    def skip(reason: str) -> None:
        summary["skipped"][reason] = summary["skipped"].get(reason, 0) + 1

    grids: dict[int, MiniGrid] = {}
    for g in client.mini_grids():
        grid = db.scalar(select(MiniGrid).where(MiniGrid.mpm_id == g["id"]))
        if grid is None:
            name = g.get("name") or f"MPM mini-grid {g['id']}"
            if db.scalar(select(MiniGrid).where(MiniGrid.name == name)):
                name = f"{name} (MPM #{g['id']})"
            grid = MiniGrid(mpm_id=g["id"], name=name, district="", source="mpm")
            db.add(grid)
        cluster = g.get("cluster") if isinstance(g.get("cluster"), dict) else {}
        grid.district = cluster.get("name") or grid.district
        grids[g["id"]] = grid
        summary["mini_grids"] += 1
    db.flush()

    areas: dict[int, ServiceArea] = {}
    for c in client.cities():
        grid = grids.get(c.get("mini_grid_id"))
        if grid is None:
            skip("city without a synced mini-grid")
            continue
        area = db.scalar(select(ServiceArea).where(ServiceArea.mpm_city_id == c["id"]))
        if area is None:
            area = ServiceArea(mpm_city_id=c["id"], code=f"M{c['id']}", source="mpm", description="Synced from MPM")
            db.add(area)
        area.name, area.mini_grid_id = c.get("name") or f"MPM city {c['id']}", grid.id
        areas[c["id"]] = area
        summary["service_areas"] += 1
    db.flush()

    seen_people: set[int] = set()
    for person in client.customers():
        address = _primary_address(person)
        area = areas.get((address or {}).get("city_id"))
        if area is None:
            skip("no primary address in a synced city")
            continue
        phone = normalize((address or {}).get("phone"), client.config.mpm_default_country_code)
        if phone is None:
            skip("missing or invalid phone number")
            continue
        customer = db.scalar(select(Customer).where(Customer.mpm_person_id == person["id"]))
        clash = db.scalar(select(Customer).where(Customer.phone == phone, Customer.mpm_person_id != person["id"]))
        if clash is not None:
            skip("phone number shared with another customer")
            continue
        if customer is None:
            customer = Customer(mpm_person_id=person["id"], source="mpm", whatsapp_opt_in=False,
                                notification_preference="whatsapp", account_status="active", created_at=t)
            db.add(customer)
            summary["customers_created"] += 1
        else:
            summary["customers_updated"] += 1
            if customer.account_status == "inactive" and customer.notes.startswith("Removed from MPM"):
                customer.account_status, customer.notes = "active", ""
        customer.name, customer.phone, customer.service_area_id = _person_name(person), phone, area.id
        customer.last_synced_at = t
        seen_people.add(person["id"])
        db.flush()
        for device in person.get("devices") or []:
            if device.get("device_type") not in (None, "meter") or not device.get("device_serial"):
                continue
            meter = db.scalar(select(Meter).where(Meter.serial == device["device_serial"]))
            if meter is None:
                meter = Meter(serial=device["device_serial"], source="mpm", status="normal", status_since=t)
                db.add(meter)
            elif meter.source != "mpm":
                skip("meter serial already used by a demo meter")
                continue
            meter.service_area_id, meter.customer_id = area.id, customer.id
            summary["meters"] += 1

    # Customers deleted in MPM are deactivated (never deleted) so their message history stays intact.
    for customer in db.scalars(select(Customer).where(Customer.source == "mpm", Customer.account_status == "active")):
        if customer.mpm_person_id not in seen_people:
            customer.account_status, customer.notes = "inactive", "Removed from MPM (deactivated by sync)"
            summary["customers_deactivated"] += 1

    activity.log(db, "mpm_sync", f"MPM sync: {summary['customers_created']} new and {summary['customers_updated']} "
                 f"updated customers, {summary['service_areas']} service areas", severity="success")
    db.commit()
    log.info("mpm sync finished: %s", summary)
    return summary
