"""Sprint 96: rename notebook cell identity column cell_id -> content_hash.

Revision ID: 019
Revises: 018
"""

from collections.abc import Sequence

from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES = (
    "notebook_outputs",
    "notebook_cell_runs",
    "notebook_cell_run_sources",
)


def upgrade() -> None:
    """Rename ``cell_id`` to ``content_hash`` across the three notebook tables.

    Sprint 96 drops the per-cell UUID from the jupytext marker and
    switches to a deterministic ``sha256(source)[:16]`` derived at
    load time.  The three persistence tables keyed on cell identity
    keep the same shape; only the column name changes so the semantics
    are legible at query time (``cell_id`` was an opaque UUID, the new
    value is a content-hash).

    Pre-Sprint-96 rows keep their UUID payload in the renamed column —
    they are orphans now (no new cell will ever compute to a UUID-
    shaped hash), but leaving them in place avoids the data-loss
    surprise of a TRUNCATE.  The natural ``clear_path`` cascade in
    :mod:`pointlessql.services.notebook_outputs` reaps them on the
    next notebook delete / rename, and no query touches them again in
    the meantime.
    """
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("cell_id", new_column_name="content_hash")


def downgrade() -> None:
    """Rename the column back to ``cell_id`` for rollback."""
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("content_hash", new_column_name="cell_id")
