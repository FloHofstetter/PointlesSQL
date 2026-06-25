"""lineage_row_rejects: extend reason CHECK with expectation_failed

Phase 36 Sprint 36.3 introduces the ``expectation_failed`` reject
reason.  It is emitted by ``services/dbt_bridge.py`` when a dbt test
reports ``status=fail`` so the cockpit + run-detail UI surface dbt
test failures alongside merge-time rejects.

Per-row failure extraction (one reject per failing source row) is
deferred — it would require ``dbt test --store-failures`` plus a
follow-up SELECT against ``dbt_test__audit.<test_name>``.  Sprint
36.3 emits one reject row per failing test instead, with the
``source_row_id`` set to the test's ``unique_id`` and ``detail``
carrying dbt's failure message.

The Python ``REJECT_REASONS`` tuple in
``pointlessql/models/lineage.py`` is updated in the same commit so
both gates agree.

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-06 13:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REASONS_NEW = (
    "on_key_null",
    "schema_mismatch",
    "duplicate_in_source",
    "merge_predicate_excluded",
    "other",
    "expectation_failed",
)
_REASONS_OLD = _REASONS_NEW[:-1]


def _ck_clause(reasons: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{r}'" for r in reasons)
    return f"reason IN ({quoted})"


def upgrade() -> None:
    """Allow the ``expectation_failed`` reject reason."""
    with op.batch_alter_table("lineage_row_rejects", recreate="auto") as batch:
        batch.drop_constraint("ck_lineage_row_rejects_reason", type_="check")
        batch.create_check_constraint(
            "ck_lineage_row_rejects_reason",
            _ck_clause(_REASONS_NEW),
        )


def downgrade() -> None:
    """Restore the merge-only reject-reason CHECK."""
    with op.batch_alter_table("lineage_row_rejects", recreate="auto") as batch:
        batch.drop_constraint("ck_lineage_row_rejects_reason", type_="check")
        batch.create_check_constraint(
            "ck_lineage_row_rejects_reason",
            _ck_clause(_REASONS_OLD),
        )
