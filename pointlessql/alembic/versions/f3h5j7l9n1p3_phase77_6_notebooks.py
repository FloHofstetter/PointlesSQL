"""phase77.6 — notebooks UUID identity table.

Pre-77.6 notebooks live as bare files on disk referenced by a
``file_path`` string.  ``NotebookOutput`` / ``NotebookCellRun`` /
``NotebookCellRunSource`` all key on ``file_path`` directly,
which means renaming a notebook breaks every social link / audit
trail / lineage edge that pointed at the old path.

77.6 adds a thin metadata table that gives every notebook a
stable UUID identity (locked decision #8 from the Phase 77 plan).
The UUID becomes the ``entity_ref`` for the social layer
(``kind='notebook'``).  ``file_path`` is preserved as a unique
column so the existing path-based routes keep working unchanged;
renaming a notebook (later) becomes a single ``UPDATE notebooks
SET file_path = ...`` instead of a lossy data migration across
five tables.

Schema:

* ``notebooks(id VARCHAR(36) PK, workspace_id INTEGER FK,
  file_path VARCHAR(500), created_at TIMESTAMP)``.
* UNIQUE on ``(workspace_id, file_path)`` so the path-based
  lookup stays an index hit.
* ``ix_notebooks_path`` for the workspace-agnostic path lookup
  used by the editor render.

Backfill: every distinct ``(workspace_id, file_path)`` pair
across ``NotebookOutput`` + ``NotebookCellRun`` +
``NotebookCellRunSource`` gets a fresh UUID4 hex.  Each table is
probed defensively because the test schema does not always
include every history table — the migration tolerates an empty
or absent source table.

Revision ID: f3h5j7l9n1p3
Revises: e2g4i6k8m0o2
Create Date: 2026-05-15 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3h5j7l9n1p3"
down_revision: str | None = "e2g4i6k8m0o2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``notebooks`` + backfill from existing path-keyed tables."""
    op.create_table(
        "notebooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("workspace_id", "file_path", name="uq_notebooks_path_per_workspace"),
    )
    op.create_index("ix_notebooks_path", "notebooks", ["file_path"])

    # Backfill — probe every history table defensively.  Only
    # ``notebook_outputs`` is guaranteed to carry ``workspace_id``;
    # ``notebook_cell_runs`` + ``notebook_cell_run_sources`` are
    # path-keyed without a workspace column, so we coalesce those
    # to workspace_id=1 (pre-Phase 28.1 single-workspace era).
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())
    seen: set[tuple[int, str]] = set()
    if "notebook_outputs" in existing:
        rows = bind.execute(
            sa.text("SELECT DISTINCT workspace_id, file_path FROM notebook_outputs")
        ).all()
        for ws_id, path in rows:
            seen.add((int(ws_id) if ws_id is not None else 1, str(path)))
    for source_table in ("notebook_cell_runs", "notebook_cell_run_sources"):
        if source_table not in existing:
            continue
        cols = {c["name"] for c in insp.get_columns(source_table)}
        if "workspace_id" in cols:
            rows = bind.execute(
                sa.text(f"SELECT DISTINCT workspace_id, file_path FROM {source_table}")
            ).all()
            for ws_id, path in rows:
                seen.add((int(ws_id) if ws_id is not None else 1, str(path)))
        else:
            rows = bind.execute(sa.text(f"SELECT DISTINCT file_path FROM {source_table}")).all()
            for (path,) in rows:
                seen.add((1, str(path)))
    if seen:
        import uuid as _uuid

        bind.execute(
            sa.text(
                "INSERT INTO notebooks (id, workspace_id, file_path) "
                "VALUES (:id, :ws_id, :file_path)"
            ),
            [
                {
                    "id": str(_uuid.uuid4()),
                    "ws_id": ws_id,
                    "file_path": path,
                }
                for ws_id, path in seen
            ],
        )


def downgrade() -> None:
    """Drop ``notebooks`` + its path index."""
    op.drop_index("ix_notebooks_path", table_name="notebooks")
    op.drop_table("notebooks")
