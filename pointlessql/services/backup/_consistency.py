"""Cross-domain consistency checks for a restored metadata DB.

After a restore the metadata DB is internally valid (Alembic-migrated), but
the lakehouse it references — Delta tables, branch tags — lives outside the
DB and may have moved on.  This module runs best-effort coherence checks
and returns a structured report rather than raising, so the operator sees
the full picture of what reconciled cleanly and what needs attention.

The checks are intentionally generic and additive: each is wrapped so a
schema the running code does not have (an older/newer table) is skipped with
a note instead of crashing the whole check.  Domain-specific checks (Delta
version reachability, orphaned branch tags) extend :data:`_CHECKS`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyReport:
    """Result of running the consistency checks.

    Attributes:
        checks_run: Names of the checks that executed.
        warnings: Soft findings worth an operator's attention.
        errors: Hard inconsistencies that likely need manual repair.
        skipped: Checks skipped because their table(s) were absent.
    """

    checks_run: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the DB passed with no hard errors."""
        return not self.errors


def _check_alembic_stamped(conn: Any, report: ConsistencyReport) -> None:
    """Assert the DB carries exactly one Alembic revision row."""
    rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    if len(rows) != 1:
        report.errors.append(f"alembic_version has {len(rows)} rows; expected exactly 1")


def _check_no_orphan_workspace_members(conn: Any, report: ConsistencyReport) -> None:
    """Workspace members must reference a live workspace + user."""
    orphans = conn.execute(
        text(
            "SELECT count(*) FROM workspace_members wm "
            "LEFT JOIN workspaces w ON wm.workspace_id = w.id "
            "WHERE w.id IS NULL"
        )
    ).scalar()
    if orphans:
        report.errors.append(f"{orphans} workspace_members row(s) reference a missing workspace")


# name -> (required_tables, check_fn).  A check is skipped (not failed) when
# any required table is absent, so the report stays honest across schema
# versions instead of crashing on a table the code does not have.
_CHECKS: dict[str, tuple[tuple[str, ...], Callable[[Any, ConsistencyReport], None]]] = {
    "alembic_stamped": (("alembic_version",), _check_alembic_stamped),
    "workspace_members_referential": (
        ("workspace_members", "workspaces"),
        _check_no_orphan_workspace_members,
    ),
}


def check_consistency(engine: Any) -> ConsistencyReport:
    """Run all consistency checks against *engine* and return the report.

    Args:
        engine: A SQLAlchemy engine bound to the metadata DB to check.

    Returns:
        A :class:`ConsistencyReport`; ``report.ok`` is ``True`` when no
        hard errors were found.
    """
    report = ConsistencyReport()
    present = set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        for name, (required, fn) in _CHECKS.items():
            if not set(required).issubset(present):
                report.skipped.append(name)
                continue
            try:
                fn(conn, report)
                report.checks_run.append(name)
            except Exception as exc:  # noqa: BLE001 — one check must not abort the rest
                report.warnings.append(f"check {name!r} raised and was skipped: {exc}")
    return report
