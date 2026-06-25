"""Repair saved_audit_queries SQLite-syntax seed on already-deployed PG

Migration ``j0e1f2a3b4c5`` originally seeded the 5 starter rows
with ``datetime('now', '-N days')``, which is SQLite-only syntax.
That seed was back-edited in Sprint 32.1 to be dialect-aware, so
fresh deployments now get the right SQL.  But existing PG
deployments already ran the old seed and have broken rows that
raise ``syntax error`` on every run.

This one-shot migration UPDATEs the affected rows in place on PG.
SQLite installs already have correct SQL; the migration is a no-op
there.

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-05 19:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (slug, days, sql_token_to_replace) — paired with the starter-row
# definitions in migration j0e1f2a3b4c5.  Keep in sync with the
# ``_starter_rows`` helper there.
_REPAIRS: list[tuple[str, int, str]] = [
    ("pii-writes-last-90d", 90, "vc.created_at >="),
    ("rollbacks-last-quarter", 90, "o.started_at >="),
    ("cost-gate-denials-this-week", 7, "started_at >="),
    ("top-mutating-principals-30d", 30, "r.started_at >="),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    conn = op.get_bind()
    for slug, days, _anchor in _REPAIRS:
        sqlite_fragment = f"datetime('now', '-{days} days')"
        pg_fragment = f"NOW() - INTERVAL '{days} days'"
        conn.execute(
            text(
                "UPDATE saved_audit_queries "
                "SET sql_text = REPLACE(sql_text, :sqlite_fragment, :pg_fragment) "
                "WHERE slug = :slug AND sql_text LIKE :pattern"
            ),
            {
                "slug": slug,
                "sqlite_fragment": sqlite_fragment,
                "pg_fragment": pg_fragment,
                "pattern": f"%{sqlite_fragment}%",
            },
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    conn = op.get_bind()
    for slug, days, _anchor in _REPAIRS:
        sqlite_fragment = f"datetime('now', '-{days} days')"
        pg_fragment = f"NOW() - INTERVAL '{days} days'"
        conn.execute(
            text(
                "UPDATE saved_audit_queries "
                "SET sql_text = REPLACE(sql_text, :pg_fragment, :sqlite_fragment) "
                "WHERE slug = :slug AND sql_text LIKE :pattern"
            ),
            {
                "slug": slug,
                "sqlite_fragment": sqlite_fragment,
                "pg_fragment": pg_fragment,
                "pattern": f"%{pg_fragment}%",
            },
        )
