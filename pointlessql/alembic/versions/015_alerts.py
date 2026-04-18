"""Sprint 55: alerts + destinations + events + users.feed_token.

Revision ID: 015
Revises: 014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Sprint-55 alerting surface.

    Three tables carry a deliberate split of responsibilities: alerts
    are the user-facing unit of configuration; alert_destinations are
    queryable per-kind so admin UIs and audits can filter without
    touching JSON; alert_events log every firing verbatim as
    CloudEvents 1.0 envelopes for replay and debug.

    ``users.feed_token`` carries a nullable unique opaque string
    that authenticates pull-feed requests.  Materialised lazily on
    first feed GET via :func:`secrets.token_urlsafe`.
    """
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=200), nullable=False, unique=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "saved_query_id",
            sa.Integer,
            sa.ForeignKey("saved_queries.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("cron_expr", sa.String(length=120), nullable=False),
        sa.Column("condition_op", sa.String(length=8), nullable=False),
        sa.Column("threshold", sa.Integer, nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "backing_job_id",
            sa.Integer,
            sa.ForeignKey("jobs.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "condition_op IN ('gt','lt','eq','ne')",
            name="ck_alerts_condition_op",
        ),
    )
    op.create_index("ix_alerts_owner", "alerts", ["owner_id"])

    op.create_table(
        "alert_destinations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "alert_id",
            sa.Integer,
            sa.ForeignKey("alerts.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("webhook_url", sa.String(length=2000), nullable=True),
        sa.Column("hmac_secret", sa.String(length=256), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('webhook','feed')",
            name="ck_alert_destinations_kind",
        ),
    )
    op.create_index(
        "ix_alert_destinations_alert", "alert_destinations", ["alert_id"]
    )
    op.create_index(
        "ix_alert_destinations_kind", "alert_destinations", ["kind"]
    )

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "alert_id",
            sa.Integer,
            sa.ForeignKey("alerts.id"),
            nullable=False,
        ),
        sa.Column(
            "event_id", sa.String(length=64), nullable=False, unique=True
        ),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.CheckConstraint(
            "outcome IN ('fired','suppressed','delivery_failed')",
            name="ck_alert_events_outcome",
        ),
    )
    op.create_index(
        "ix_alert_events_fired", "alert_events", ["alert_id", "fired_at"]
    )

    op.add_column(
        "users",
        sa.Column("feed_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_users_feed_token",
        "users",
        ["feed_token"],
        unique=True,
        sqlite_where=sa.text("feed_token IS NOT NULL"),
        postgresql_where=sa.text("feed_token IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the Sprint-55 alerting surface in reverse order."""
    op.drop_index("ix_users_feed_token", table_name="users")
    op.drop_column("users", "feed_token")
    op.drop_index("ix_alert_events_fired", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index(
        "ix_alert_destinations_kind", table_name="alert_destinations"
    )
    op.drop_index(
        "ix_alert_destinations_alert", table_name="alert_destinations"
    )
    op.drop_table("alert_destinations")
    op.drop_index("ix_alerts_owner", table_name="alerts")
    op.drop_table("alerts")
