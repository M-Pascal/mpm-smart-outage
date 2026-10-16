"""Message templates and rendering.

Bodies use {placeholders}. They are written so they can later be registered as
WhatsApp Business *template messages* (business-initiated messages need
pre-approved templates); the placeholder names map to template parameters.
"""
from __future__ import annotations

import re
from typing import Any

DEFAULT_TEMPLATES: list[dict[str, str]] = [
    {
        "key": "scheduled_maintenance_notice",
        "name": "Scheduled maintenance notice",
        "category": "planned",
        "description": "First notice sent when a planned interruption is published.",
        "body": (
            "*{organization} Notice*\n\nDear Customer,\n\n"
            "Please be informed that electricity supply in {area} will be temporarily interrupted on {date}, "
            "from {start_time} to {end_time}, due to {reason}.\n\n"
            "We apologize for the inconvenience and encourage you to plan accordingly.\n\nThank you."
        ),
    },
    {
        "key": "maintenance_reminder",
        "name": "Maintenance reminder",
        "category": "planned",
        "description": "Reminder sent at the configured time before the interruption.",
        "body": (
            "*{organization} Reminder*\n\nDear Customer,\n\n"
            "This is a reminder that electricity supply in {area} will be interrupted in about {time_until}, "
            "on {date} from {start_time} to {end_time}, due to {reason}.\n\n"
            "Please plan accordingly.\n\nThank you."
        ),
    },
    {
        "key": "maintenance_rescheduled",
        "name": "Maintenance rescheduling",
        "category": "planned",
        "description": "Sent when the time of an already-announced interruption changes.",
        "body": (
            "*{organization} Schedule Update*\n\nDear Customer,\n\n"
            "The planned electricity interruption in {area}, previously scheduled for {old_date} from "
            "{old_start_time} to {old_end_time}, has been rescheduled to {date}, from {start_time} to {end_time}.\n\n"
            "We apologize for any inconvenience.\n\nThank you."
        ),
    },
    {
        "key": "maintenance_cancelled",
        "name": "Maintenance cancellation",
        "category": "planned",
        "description": "Sent when an already-announced interruption is cancelled.",
        "body": (
            "*{organization} Schedule Update*\n\nDear Customer,\n\n"
            "The planned electricity interruption in {area} scheduled for {date} from {start_time} to {end_time} "
            "has been cancelled. Electricity supply will continue as normal.\n\nThank you."
        ),
    },
    {
        "key": "unexpected_outage",
        "name": "Unexpected outage announcement",
        "category": "unplanned",
        "description": "Sent when an unexpected interruption is confirmed.",
        "body": (
            "*{organization} Power Alert*\n\nDear Customer,\n\n"
            "An unexpected electricity interruption has been confirmed in your service area ({area}).\n\n"
            "Our technical team is investigating the issue.\n\n"
            "We will provide further updates when reliable information becomes available.\n\n"
            "Thank you for your patience."
        ),
    },
    {
        "key": "extended_outage_update",
        "name": "Extended outage update",
        "category": "unplanned",
        "description": "Optional update when an outage lasts longer than expected.",
        "body": (
            "*{organization} Outage Update*\n\nDear Customer,\n\n"
            "The electricity interruption in {area} is taking longer than expected. Our technical team is still "
            "working on the issue. Estimated restoration: {eta}.\n\n"
            "We will keep you informed.\n\nThank you for your patience."
        ),
    },
    {
        "key": "power_restored",
        "name": "Power restoration announcement (optional)",
        "category": "unplanned",
        "description": "Only sent when an operator decides it is useful, e.g. after a widespread outage.",
        "body": (
            "*{organization} Power Update*\n\nDear Customer,\n\n"
            "Electricity supply in {area} has been restored. If you are still without power, please contact "
            "our customer service.\n\nThank you for your patience."
        ),
    },
    {
        "key": "general_announcement",
        "name": "General announcement",
        "category": "general",
        "description": "Free-text announcement to selected service areas.",
        "body": "*{organization} Notice*\n\nDear Customer,\n\n{message}\n\nThank you.",
    },
]

TEMPLATE_KEYS = {t["key"] for t in DEFAULT_TEMPLATES}

PLACEHOLDERS: dict[str, str] = {
    "organization": "Organisation name from settings",
    "customer_name": "Recipient name (avoid in shared or public messages)",
    "area": "Recipient's service area",
    "title": "Planned event title",
    "reason": "Reason for the interruption",
    "date": "Start date, e.g. 20 October 2026",
    "start_time": "Start time, e.g. 9:00 AM",
    "end_time": "Expected restoration time",
    "end_date": "Expected restoration date",
    "time_until": "Time remaining until the start",
    "old_date": "Previous date (rescheduling)",
    "old_start_time": "Previous start time (rescheduling)",
    "old_end_time": "Previous end time (rescheduling)",
    "eta": "Estimated restoration (outage update)",
    "message": "Free text (general announcement)",
}

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def render(body: str, context: dict[str, Any]) -> str:
    """Fill {placeholders}; unknown or missing ones are left visible so mistakes are obvious."""
    return _PLACEHOLDER.sub(lambda m: str(context[m.group(1)]) if context.get(m.group(1)) not in (None, "") else m.group(0), body)


def unknown_placeholders(body: str) -> list[str]:
    return sorted({p for p in _PLACEHOLDER.findall(body) if p not in PLACEHOLDERS})


def missing_placeholders(rendered: str) -> list[str]:
    return sorted(set(_PLACEHOLDER.findall(rendered)))
