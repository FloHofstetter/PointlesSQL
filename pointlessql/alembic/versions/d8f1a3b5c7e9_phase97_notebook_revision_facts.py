"""phase97_rest — pin-to-memory notebook revision facts

Adds the Phase-97-Rest *pin-to-memory* primitive:

* New ``notebook_revision_facts`` table that promotes a frozen
  :class:`NotebookRevision` into a referenceable fact with title +
  optional description + optional cell-output snapshot.  Soft-delete
  via ``unpinned_at`` keeps the row history while hiding from the
  active list; the partial UNIQUE filter on
  ``unpinned_at IS NULL`` keeps ``pin`` idempotent.
* Extends ``ck_social_targets_kind`` with two new polymorphic kinds —
  ``'notebook_revision'`` (whole-revision facts) and
  ``'notebook_cell_output'`` (per-cell-output facts).
* Extends ``ck_agent_run_operations_op_name`` with ``'pin_fact'`` so
  agent-driven ``pql.facts.pin()`` calls can record an op row.

The ``OpName`` Python StrEnum in ``pointlessql.types._enums`` adds
``PIN_FACT`` in the same commit so the :data:`VALID_OP_NAMES` frozen
set (derived from the enum) stays in lockstep with the DB-side CHECK.

Revision ID: d8f1a3b5c7e9
Revises: c4e7a91b2f60
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8f1a3b5c7e9"
down_revision: str | None = "c4e7a91b2f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OLD_SOCIAL_KINDS_SQL = (
    "entity_kind IN ("
    "'dp', 'table', 'schema', 'catalog', "
    "'model', 'branch', 'run', 'query', "
    "'notebook', 'saved_query', 'issue', "
    "'workspace', 'agent_memory', 'notebook_cell'"
    ")"
)

_NEW_SOCIAL_KINDS_SQL = (
    "entity_kind IN ("
    "'dp', 'table', 'schema', 'catalog', "
    "'model', 'branch', 'run', 'query', "
    "'notebook', 'saved_query', 'issue', "
    "'workspace', 'agent_memory', 'notebook_cell', "
    "'notebook_revision', 'notebook_cell_output'"
    ")"
)


_OP_NAMES_OLD = (
    "autoload",
    "merge",
    "write_table",
    "sql",
    "aggregate",
    "rollback",
    "train_model",
    "branch_create",
    "branch_promote",
    "branch_discard",
    "dbt_model",
    "dbt_test",
    "sql_explain",
    "update",
    "delete",
    "drop_table",
    "create_schema",
    "drop_schema",
    "alter_table",
    "vector_index",
    "vector_search",
)
_OP_NAMES_NEW = (*_OP_NAMES_OLD, "pin_fact")


def _op_name_ck(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Create the facts table + extend the two CHECK constraints."""
    op.create_table(
        "notebook_revision_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fact_uuid", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("social_target_id", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("cell_content_hash", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description_md", sa.Text(), nullable=True),
        sa.Column("result_snapshot_json", sa.Text(), nullable=True),
        sa.Column("pinned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("pinned_by_agent_id", sa.String(length=128), nullable=True),
        sa.Column(
            "pinned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("unpinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["social_target_id"], ["social_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["notebook_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pinned_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fact_uuid"),
    )
    with op.batch_alter_table("notebook_revision_facts", schema=None) as batch_op:
        # Partial UNIQUE on the active row so re-pin after unpin
        # mints a fresh row instead of colliding with the tombstone.
        batch_op.create_index(
            "uq_notebook_revision_facts_active",
            ["workspace_id", "revision_id", "cell_content_hash"],
            unique=True,
            sqlite_where=sa.text("unpinned_at IS NULL"),
            postgresql_where=sa.text("unpinned_at IS NULL"),
        )
        batch_op.create_index(
            "ix_notebook_revision_facts_workspace_pinned",
            ["workspace_id", "pinned_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_notebook_revision_facts_revision",
            ["revision_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_notebook_revision_facts_uuid",
            ["fact_uuid"],
            unique=False,
        )

    with op.batch_alter_table("social_targets") as batch_op:
        batch_op.drop_constraint("ck_social_targets_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_social_targets_kind",
            sa.text(_NEW_SOCIAL_KINDS_SQL),
        )

    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _op_name_ck(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Drop the facts table + revert both CHECK constraints."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _op_name_ck(_OP_NAMES_OLD),
        )

    with op.batch_alter_table("social_targets") as batch_op:
        batch_op.drop_constraint("ck_social_targets_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_social_targets_kind",
            sa.text(_OLD_SOCIAL_KINDS_SQL),
        )

    with op.batch_alter_table("notebook_revision_facts", schema=None) as batch_op:
        batch_op.drop_index("ix_notebook_revision_facts_uuid")
        batch_op.drop_index("ix_notebook_revision_facts_revision")
        batch_op.drop_index("ix_notebook_revision_facts_workspace_pinned")
        batch_op.drop_index("uq_notebook_revision_facts_active")
    op.drop_table("notebook_revision_facts")
