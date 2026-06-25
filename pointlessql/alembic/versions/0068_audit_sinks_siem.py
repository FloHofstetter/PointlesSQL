"""audit_sinks: add stdout_json + syslog types

Extends the ``ck_audit_sinks_type`` CHECK so admins can wire two
new SIEM-style sink types alongside the existing webhook / s3 /
aws_cloudtrail trio.  No new column — both new sinks read their
runtime config from the existing ``config_json`` field.

Revision ID: 0068
Revises: 0067
Create Date: 2026-05-15 01:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0068"
down_revision: str | None = "0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_TYPES = "type IN ('webhook','s3','aws_cloudtrail','stdout_json','syslog')"
_OLD_TYPES = "type IN ('webhook','s3','aws_cloudtrail')"


def upgrade() -> None:
    """Replace ``ck_audit_sinks_type`` to allow the two new types."""
    with op.batch_alter_table("audit_sinks") as batch_op:
        batch_op.drop_constraint("ck_audit_sinks_type", type_="check")
        batch_op.create_check_constraint(
            "ck_audit_sinks_type",
            _NEW_TYPES,
        )


def downgrade() -> None:
    """Restore the original 3-type CHECK."""
    with op.batch_alter_table("audit_sinks") as batch_op:
        batch_op.drop_constraint("ck_audit_sinks_type", type_="check")
        batch_op.create_check_constraint(
            "ck_audit_sinks_type",
            _OLD_TYPES,
        )
