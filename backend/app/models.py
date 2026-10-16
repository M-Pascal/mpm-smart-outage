"""SQLAlchemy models. Portable types only (SQLite now, PostgreSQL later)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .clock import now
from .db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


# --------------------------------------------------------------------- grid
class MiniGrid(Base):
    __tablename__ = "mini_grids"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    district: Mapped[str] = mapped_column(String(120))
    capacity_kw: Mapped[float] = mapped_column(Float, default=0)
    service_areas: Mapped[list["ServiceArea"]] = relationship(back_populates="mini_grid", order_by="ServiceArea.code")


class ServiceArea(TimestampMixin, Base):
    __tablename__ = "service_areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    mini_grid_id: Mapped[int] = mapped_column(ForeignKey("mini_grids.id"))
    # Simulation only: forces every meter in the area into a scenario.
    sim_scenario: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    mini_grid: Mapped[MiniGrid] = relationship(back_populates="service_areas")
    customers: Mapped[list["Customer"]] = relationship(back_populates="service_area")
    meters: Mapped[list["Meter"]] = relationship(back_populates="service_area")


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(20), unique=True)  # E.164
    service_area_id: Mapped[int] = mapped_column(ForeignKey("service_areas.id"), index=True)
    customer_type: Mapped[str] = mapped_column(String(30), default="residential")
    notification_preference: Mapped[str] = mapped_column(String(20), default="whatsapp")  # whatsapp | sms | none
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    account_status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended | inactive
    notes: Mapped[str] = mapped_column(Text, default="")

    service_area: Mapped[ServiceArea] = relationship(back_populates="customers")
    meter: Mapped[Optional["Meter"]] = relationship(back_populates="customer", uselist=False)


class Meter(TimestampMixin, Base):
    __tablename__ = "meters"
    id: Mapped[int] = mapped_column(primary_key=True)
    serial: Mapped[str] = mapped_column(String(40), unique=True)
    service_area_id: Mapped[int] = mapped_column(ForeignKey("service_areas.id"), index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal")  # normal | low_voltage | no_supply | offline
    last_voltage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_current: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_power_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_reading_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_persisted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Detector state (debounce) is persisted so detection survives restarts.
    pending_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_since: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status_since: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sim_scenario: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    service_area: Mapped[ServiceArea] = relationship(back_populates="meters")
    customer: Mapped[Optional[Customer]] = relationship(back_populates="meter")


class MeterReading(Base):
    __tablename__ = "meter_readings"
    __table_args__ = (Index("ix_meter_readings_meter_ts", "meter_id", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    voltage: Mapped[float] = mapped_column(Float)
    current: Mapped[float] = mapped_column(Float)
    power_kw: Mapped[float] = mapped_column(Float)


class AreaReading(Base):
    """Per-area aggregate used for trend charts."""
    __tablename__ = "area_readings"
    __table_args__ = (Index("ix_area_readings_area_ts", "service_area_id", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    service_area_id: Mapped[int] = mapped_column(ForeignKey("service_areas.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    avg_voltage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_power_kw: Mapped[float] = mapped_column(Float, default=0)
    meters_reporting: Mapped[int] = mapped_column(Integer, default=0)
    meters_no_supply: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------- planned outages
scheduled_outage_areas = Table(
    "scheduled_outage_areas",
    Base.metadata,
    Column("scheduled_outage_id", ForeignKey("scheduled_outages.id", ondelete="CASCADE"), primary_key=True),
    Column("service_area_id", ForeignKey("service_areas.id", ondelete="CASCADE"), primary_key=True),
)


class ScheduledOutage(TimestampMixin, Base):
    __tablename__ = "scheduled_outages"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(String(40))
    reason_detail: Mapped[str] = mapped_column(String(200), default="")
    mini_grid_id: Mapped[int] = mapped_column(ForeignKey("mini_grids.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # low | medium | high | critical
    # draft | scheduled | notification_queued | in_progress | completed | cancelled
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    reminder_offsets: Mapped[list[int]] = mapped_column(JSON, default=list)  # minutes before start
    send_notice_on_publish: Mapped[bool] = mapped_column(Boolean, default=True)
    customers_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(300), default="")
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)

    mini_grid: Mapped[MiniGrid] = relationship()
    service_areas: Mapped[list[ServiceArea]] = relationship(secondary=scheduled_outage_areas, order_by="ServiceArea.code")


# ---------------------------------------------------------------- incidents
class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    service_area_id: Mapped[int] = mapped_column(ForeignKey("service_areas.id"), index=True)
    scope: Mapped[str] = mapped_column(String(10), default="meter")  # meter | area
    severity: Mapped[str] = mapped_column(String(10), default="low")  # low | medium | high | critical
    verification_status: Mapped[str] = mapped_column(String(15), default="potential")  # potential | confirmed | rejected
    resolution_status: Mapped[str] = mapped_column(String(15), default="open", index=True)  # open | investigating | resolved
    confirmation_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # auto | manual
    first_evidence_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    power_restored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    affected_meter_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    peak_affected_meters: Mapped[int] = mapped_column(Integer, default=0)
    estimated_customers: Mapped[int] = mapped_column(Integer, default=0)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)

    service_area: Mapped[ServiceArea] = relationship()
    events: Mapped[list["IncidentEvent"]] = relationship(back_populates="incident", order_by="IncidentEvent.ts",
                                                         cascade="all, delete-orphan")


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    incident: Mapped[Incident] = relationship(back_populates="events")


# ------------------------------------------------------------ notifications
class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(20))  # planned | unplanned | general
    description: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class NotificationJob(Base):
    """One scheduled communication to one or more service areas."""
    __tablename__ = "notification_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    # notice | reminder | reschedule | cancellation | outage_alert | outage_update | restoration | manual
    kind: Mapped[str] = mapped_column(String(20))
    template_key: Mapped[str] = mapped_column(String(60))
    scheduled_outage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scheduled_outages.id"), nullable=True, index=True)
    incident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incidents.id"), nullable=True, index=True)
    area_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    send_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    offset_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # draft | scheduled | processing | simulated_sent | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    scheduled_outage: Mapped[Optional[ScheduledOutage]] = relationship()
    incident: Mapped[Optional[Incident]] = relationship()
    messages: Mapped[list["NotificationMessage"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class NotificationMessage(Base):
    """Per-recipient history. The unique constraint makes duplicate sends impossible."""
    __tablename__ = "notification_messages"
    __table_args__ = (UniqueConstraint("job_id", "customer_id", name="uq_message_job_customer"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("notification_jobs.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    phone: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # simulated_sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str] = mapped_column(String(300), default="")
    simulated_message_id: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    job: Mapped[NotificationJob] = relationship(back_populates="messages")
    customer: Mapped[Customer] = relationship()


# ------------------------------------------------------------ misc / audit
class ActivityLog(Base):
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info | success | warning | critical
    message: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    operator_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
