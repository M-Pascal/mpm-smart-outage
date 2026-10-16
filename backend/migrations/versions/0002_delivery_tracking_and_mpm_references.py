"""Delivery tracking, webhook idempotency and MicroPowerManager references.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _source_columns(batch_op) -> None:  # noqa: ANN001
    batch_op.add_column(sa.Column("source", sa.String(length=10), nullable=False, server_default="demo"))


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("event_key", name="uq_webhook_events_event_key"),
    )
    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("notification_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("error_message", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_delivery_attempts_message_id", "delivery_attempts", ["message_id"])

    with op.batch_alter_table("mini_grids") as batch_op:
        _source_columns(batch_op)
        batch_op.add_column(sa.Column("mpm_id", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint("uq_mini_grids_mpm_id", ["mpm_id"])

    with op.batch_alter_table("service_areas") as batch_op:
        _source_columns(batch_op)
        batch_op.add_column(sa.Column("mpm_city_id", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint("uq_service_areas_mpm_city_id", ["mpm_city_id"])

    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("consent_source", sa.String(length=30), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("consent_updated_at", sa.DateTime(), nullable=True))
        _source_columns(batch_op)
        batch_op.add_column(sa.Column("mpm_person_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_synced_at", sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint("uq_customers_mpm_person_id", ["mpm_person_id"])

    with op.batch_alter_table("meters") as batch_op:
        _source_columns(batch_op)

    with op.batch_alter_table("incidents") as batch_op:
        batch_op.add_column(sa.Column("evidence_type", sa.String(length=20), nullable=False, server_default="voltage"))

    with op.batch_alter_table("notification_jobs") as batch_op:
        batch_op.add_column(sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table("notification_messages") as batch_op:
        batch_op.add_column(sa.Column("channel", sa.String(length=20), nullable=False, server_default="whatsapp"))
        batch_op.add_column(sa.Column("provider", sa.String(length=20), nullable=False, server_default="mock"))
        batch_op.add_column(sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("provider_message_id", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("error_code", sa.String(length=40), nullable=False, server_default=""))
        for column in ("next_retry_at", "sent_at", "delivered_at", "read_at", "failed_at"):
            batch_op.add_column(sa.Column(column, sa.DateTime(), nullable=True))

    # Existing history was produced by the simulator: keep it, labelled as simulated.
    op.execute("UPDATE notification_messages SET provider_message_id = simulated_message_id, sent_at = created_at "
               "WHERE simulated_message_id <> ''")
    op.execute("UPDATE notification_messages SET status = 'sent' WHERE status = 'simulated_sent'")
    op.execute("UPDATE notification_messages SET failed_at = updated_at WHERE status = 'failed'")
    op.execute("UPDATE notification_jobs SET status = 'sent' WHERE status = 'simulated_sent'")

    with op.batch_alter_table("notification_messages") as batch_op:
        batch_op.drop_column("simulated_message_id")
        batch_op.create_unique_constraint("uq_notification_messages_provider_message_id", ["provider_message_id"])
        batch_op.create_index("ix_notification_messages_status", ["status"])
        batch_op.create_index("ix_notification_messages_next_retry_at", ["next_retry_at"])


def downgrade() -> None:
    with op.batch_alter_table("notification_messages") as batch_op:
        batch_op.add_column(sa.Column("simulated_message_id", sa.String(length=60), nullable=False, server_default=""))
    op.execute("UPDATE notification_messages SET simulated_message_id = COALESCE(provider_message_id, '')")
    op.execute("UPDATE notification_messages SET status = 'simulated_sent' WHERE status IN ('sent', 'delivered', 'read')")
    op.execute("UPDATE notification_jobs SET status = 'simulated_sent' WHERE status = 'sent'")
    with op.batch_alter_table("notification_messages") as batch_op:
        batch_op.drop_index("ix_notification_messages_next_retry_at")
        batch_op.drop_index("ix_notification_messages_status")
        batch_op.drop_constraint("uq_notification_messages_provider_message_id", type_="unique")
        for column in ("failed_at", "read_at", "delivered_at", "sent_at", "next_retry_at", "error_code",
                       "provider_message_id", "simulated", "provider", "channel"):
            batch_op.drop_column(column)
    with op.batch_alter_table("notification_jobs") as batch_op:
        batch_op.drop_column("simulated")
    with op.batch_alter_table("incidents") as batch_op:
        batch_op.drop_column("evidence_type")
    with op.batch_alter_table("meters") as batch_op:
        batch_op.drop_column("source")
    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_constraint("uq_customers_mpm_person_id", type_="unique")
        for column in ("last_synced_at", "mpm_person_id", "source", "consent_updated_at", "consent_source"):
            batch_op.drop_column(column)
    with op.batch_alter_table("service_areas") as batch_op:
        batch_op.drop_constraint("uq_service_areas_mpm_city_id", type_="unique")
        batch_op.drop_column("mpm_city_id")
        batch_op.drop_column("source")
    with op.batch_alter_table("mini_grids") as batch_op:
        batch_op.drop_constraint("uq_mini_grids_mpm_id", type_="unique")
        batch_op.drop_column("mpm_id")
        batch_op.drop_column("source")
    op.drop_index("ix_delivery_attempts_message_id", table_name="delivery_attempts")
    op.drop_table("delivery_attempts")
    op.drop_table("webhook_events")
