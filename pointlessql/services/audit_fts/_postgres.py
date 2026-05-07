"""Postgres-side FTS layer for the audit lake.

Owns the ``audit_search_index`` table layout, the per-source PL/pgSQL
upsert + delete trigger functions, the ``ts_rank`` /
``plainto_tsquery`` search, and the rebuild path.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from pointlessql.services.audit_fts import logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


_PG_AXES: tuple[str, ...] = ("runs", "ops", "queries", "tool_calls", "audit_log")


_PG_TRIGGER_SPECS: dict[str, dict[str, str]] = {
    "runs": {
        "table": "agent_runs",
        "entity_col": "id",
        "run_id_expr": "NEW.id",
        "principal_expr": "COALESCE(NEW.principal, '')",
        "table_fqn_expr": "''",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.id::text, '') || ' ' || COALESCE(NEW.principal, '') "
            "|| ' ' || COALESCE(NEW.agent_id, '') || ' ' || COALESCE(NEW.status, '') "
            "|| ' ' || COALESCE(NEW.denied_reason, '') "
            "|| ' ' || COALESCE(NEW.tables_touched, '') "
            "|| ' ' || COALESCE(NEW.notebook_path, '')"
        ),
    },
    "ops": {
        "table": "agent_run_operations",
        "entity_col": "id",
        "run_id_expr": "COALESCE(NEW.agent_run_id, '')",
        "principal_expr": "''",
        "table_fqn_expr": "COALESCE(NEW.target_table, '')",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.op_name, '') || ' ' || COALESCE(NEW.target_table, '') "
            "|| ' ' || COALESCE(NEW.error_message, '') "
            "|| ' ' || COALESCE(NEW.params_json, '')"
        ),
    },
    "queries": {
        "table": "query_history",
        "entity_col": "id",
        "run_id_expr": "COALESCE(NEW.agent_run_id, '')",
        "principal_expr": "COALESCE(NEW.user_email, '')",
        "table_fqn_expr": "''",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.sql_text, '') || ' ' || COALESCE(NEW.user_email, '') "
            "|| ' ' || COALESCE(NEW.read_kind, '') || ' ' || COALESCE(NEW.status, '')"
        ),
    },
    "tool_calls": {
        "table": "agent_run_tool_calls",
        "entity_col": "id",
        "run_id_expr": "COALESCE(NEW.agent_run_id, '')",
        "principal_expr": "''",
        "table_fqn_expr": "''",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.tool_name, '') || ' ' || COALESCE(NEW.args_json, '') "
            "|| ' ' || COALESCE(NEW.result_summary, '')"
        ),
    },
    "audit_log": {
        "table": "audit_log",
        "entity_col": "id",
        "run_id_expr": "''",
        "principal_expr": "COALESCE(NEW.user_email, '')",
        "table_fqn_expr": "COALESCE(NEW.target, '')",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.action, '') || ' ' || COALESCE(NEW.target, '') "
            "|| ' ' || COALESCE(NEW.detail, '') || ' ' || COALESCE(NEW.user_email, '')"
        ),
    },
}


#: The generated tsvector pre-replaces ``.`` / ``_`` / ``-`` /
#: ``@`` with spaces so PG's ``simple`` parser splits UC FQNs and
#: email addresses into searchable parts.  This mirrors the
#: SQLite FTS5 ``unicode61 separators '._-'`` tokenizer config and
#: keeps cross-dialect search behaviour consistent — without it,
#: ``alice@example.com`` would tokenize as a single email token on
#: PG but as three tokens on SQLite.
_PG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_search_index (
    axis TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    run_id TEXT,
    principal TEXT,
    table_fqn TEXT,
    workspace_id INTEGER,
    text_corpus TEXT,
    text_search TSVECTOR GENERATED ALWAYS AS
        (to_tsvector('simple',
            regexp_replace(COALESCE(text_corpus, ''), '[._@\\-]+', ' ', 'g'))) STORED,
    PRIMARY KEY (axis, entity_id)
)
"""


_PG_INITIAL_POPULATE_SQL: dict[str, str] = {
    "runs": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'runs', id::text, id, COALESCE(principal, ''), '', "
        "       COALESCE(workspace_id, 1), "
        "       COALESCE(id::text, '') || ' ' || COALESCE(principal, '') || ' ' || "
        "       COALESCE(agent_id, '') || ' ' || COALESCE(status, '') || ' ' || "
        "       COALESCE(denied_reason, '') || ' ' || COALESCE(tables_touched, '') || ' ' || "
        "       COALESCE(notebook_path, '') "
        "FROM agent_runs ON CONFLICT DO NOTHING"
    ),
    "ops": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'ops', id::text, COALESCE(agent_run_id, ''), '', "
        "       COALESCE(target_table, ''), COALESCE(workspace_id, 1), "
        "       COALESCE(op_name, '') || ' ' || COALESCE(target_table, '') || ' ' || "
        "       COALESCE(error_message, '') || ' ' || COALESCE(params_json, '') "
        "FROM agent_run_operations ON CONFLICT DO NOTHING"
    ),
    "queries": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'queries', id::text, COALESCE(agent_run_id, ''), "
        "       COALESCE(user_email, ''), '', COALESCE(workspace_id, 1), "
        "       COALESCE(sql_text, '') || ' ' || COALESCE(user_email, '') || ' ' || "
        "       COALESCE(read_kind, '') || ' ' || COALESCE(status, '') "
        "FROM query_history ON CONFLICT DO NOTHING"
    ),
    "tool_calls": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'tool_calls', id::text, COALESCE(agent_run_id, ''), '', '', "
        "       COALESCE(workspace_id, 1), "
        "       COALESCE(tool_name, '') || ' ' || COALESCE(args_json, '') || ' ' || "
        "       COALESCE(result_summary, '') "
        "FROM agent_run_tool_calls ON CONFLICT DO NOTHING"
    ),
    "audit_log": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'audit_log', id::text, '', COALESCE(user_email, ''), "
        "       COALESCE(target, ''), COALESCE(workspace_id, 1), "
        "       COALESCE(action, '') || ' ' || COALESCE(target, '') || ' ' || "
        "       COALESCE(detail, '') || ' ' || COALESCE(user_email, '') "
        "FROM audit_log ON CONFLICT DO NOTHING"
    ),
}


def _pg_upsert_function_sql(axis: str, spec: dict[str, str]) -> str:
    """Build the PL/pgSQL upsert function for a single source axis."""
    return f"""
CREATE OR REPLACE FUNCTION audit_search_{axis}_upsert() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_search_index (
        axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus
    ) VALUES (
        '{axis}',
        NEW.{spec["entity_col"]}::text,
        ({spec["run_id_expr"]})::text,
        ({spec["principal_expr"]})::text,
        ({spec["table_fqn_expr"]})::text,
        ({spec["workspace_id_expr"]})::int,
        ({spec["text_expr"]})::text
    )
    ON CONFLICT (axis, entity_id) DO UPDATE SET
        run_id = EXCLUDED.run_id,
        principal = EXCLUDED.principal,
        table_fqn = EXCLUDED.table_fqn,
        workspace_id = EXCLUDED.workspace_id,
        text_corpus = EXCLUDED.text_corpus;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def _pg_delete_function_sql(axis: str, spec: dict[str, str]) -> str:
    """Build the PL/pgSQL delete function for a single source axis."""
    return f"""
CREATE OR REPLACE FUNCTION audit_search_{axis}_delete() RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM audit_search_index
        WHERE axis = '{axis}' AND entity_id = OLD.{spec["entity_col"]}::text;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
"""


def _pg_attach_trigger_sql(axis: str, spec: dict[str, str]) -> list[str]:
    """Drop-and-recreate triggers on the source table for one axis."""
    table = spec["table"]
    return [
        f"DROP TRIGGER IF EXISTS audit_search_{axis}_aiu ON {table}",
        f"DROP TRIGGER IF EXISTS audit_search_{axis}_ad ON {table}",
        (
            f"CREATE TRIGGER audit_search_{axis}_aiu "
            f"AFTER INSERT OR UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION audit_search_{axis}_upsert()"
        ),
        (
            f"CREATE TRIGGER audit_search_{axis}_ad "
            f"AFTER DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION audit_search_{axis}_delete()"
        ),
    ]


_PG_MARK_MERGE = re.compile(r"</mark>([._\-]+)<mark>")


def _merge_pg_marks(snippet: str | None) -> str | None:
    r"""Merge adjacent ``</mark>SEP<mark>`` patterns into one mark span.

    PG's ``ts_headline`` highlights individual tsquery matches.
    With the pre-replacement of ``[._@\\-]+``, a user-typed
    ``customer_marker_xyz`` matches three separate tokens, so the
    rendered snippet looks like
    ``<mark>customer</mark>_<mark>marker</mark>_<mark>xyz</mark>``.
    SQLite FTS5's ``snippet()`` returns
    ``<mark>customer_marker_xyz</mark>`` instead — the entire
    substring as one mark — because it indexes at separator-
    boundaries but renders against the original text.

    Cross-dialect parity matters for tests that grep snippets
    for ``customer_marker_xyz`` after a search; this helper
    smooths the PG output to match SQLite's by collapsing
    adjacent mark spans separated only by ``.``/``_``/``-``.
    """
    if snippet is None:
        return None
    return _PG_MARK_MERGE.sub(lambda m: m.group(1), snippet)


def is_available(session: Session) -> bool:
    """Return ``True`` when the PG ``audit_search_index`` table exists."""
    try:
        result = session.execute(
            text("SELECT to_regclass('public.audit_search_index') IS NOT NULL AS exists")
        ).first()
    except Exception:  # noqa: BLE001 — best-effort probe
        # bare-broad-ok: missing table means FTS is unavailable
        return False
    return bool(result and result[0])


def search(
    session: Session,
    *,
    sanitised: str,
    axis: str,
    limit: int,
    workspace_id: int | None,
) -> list[dict[str, Any]] | None:
    """Postgres path: ``text_search @@ plainto_tsquery``.

    The rank field flips orientation between backends: SQLite FTS5
    rank-ascending (lower=better), PG ``ts_rank`` higher=better.
    Callers iterate the returned list which is already sorted, so
    the API contract holds; we keep the raw value so audit-tooling
    can sort it explicitly if needed.
    """
    if not is_available(session):
        return None

    # Mirror the index-side pre-replacement so the user query
    # tokenizes the same way as ``text_corpus`` did at insert time
    # — UC FQNs and email addresses split into searchable parts.
    pg_query = re.sub(r"[._@\-]+", " ", sanitised).strip()
    if not pg_query:
        return None
    params: dict[str, Any] = {"query": pg_query, "limit": limit}
    sql_parts: list[str] = [
        "SELECT s.axis, s.entity_id, s.run_id, s.principal, s.table_fqn, "
        "       s.workspace_id, "
        "       ts_headline('simple', COALESCE(s.text_corpus, ''), "
        "                   plainto_tsquery('simple', :query), "
        "                   'StartSel=<mark>, StopSel=</mark>, "
        "                    MaxFragments=1, MaxWords=16, MinWords=4') "
        "         AS snippet, "
        "       ts_rank(s.text_search, plainto_tsquery('simple', :query)) "
        "         AS rank "
        "FROM audit_search_index s "
        "WHERE s.text_search @@ plainto_tsquery('simple', :query)"
    ]
    if axis != "all":
        sql_parts.append("AND s.axis = :axis")
        params["axis"] = axis
    if workspace_id is not None:
        sql_parts.append("AND s.workspace_id = :workspace_id")
        params["workspace_id"] = workspace_id
    sql_parts.append("ORDER BY rank DESC LIMIT :limit")
    sql = " ".join(sql_parts)

    try:
        rows = session.execute(text(sql), params).all()
    except Exception:  # noqa: BLE001 — bad query surfaces here
        logger.exception("audit_search_index match failed for %r", sanitised)
        return None

    return [
        {
            "axis": row.axis,
            "entity_id": row.entity_id,
            "run_id": row.run_id or None,
            "principal": row.principal or None,
            "table_fqn": row.table_fqn or None,
            "workspace_id": int(row.workspace_id) if row.workspace_id is not None else 1,
            "snippet": _merge_pg_marks(row.snippet),
            "rank": float(row.rank) if row.rank is not None else None,
        }
        for row in rows
    ]


def install_index(session: Session) -> bool:
    """Install (or re-attach) the PG FTS surface idempotently.

    The table + GIN index are created once per DB lifetime
    (``CREATE TABLE / INDEX IF NOT EXISTS``).  The trigger
    functions + triggers are *always* re-created because test
    fixtures drop the source tables (``Base.metadata.drop_all``)
    between tests — that drops the triggers via PG's
    drop-dependent-object cascade, but leaves
    ``audit_search_index`` alone (it isn't in ORM metadata) and
    leaves the trigger *functions* alone too.  Re-attaching the
    triggers via ``DROP TRIGGER IF EXISTS`` + ``CREATE TRIGGER``
    is cheap and the only correctness-preserving option.

    Args:
        session: SQLAlchemy session bound to the PG engine.

    Returns:
        ``True`` when the table was newly created (first install);
        ``False`` when only the triggers were re-attached.
    """
    table_already_existed = is_available(session)
    if not table_already_existed:
        session.execute(text(_PG_TABLE_SQL))
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_audit_search_text_search "
                "ON audit_search_index USING gin(text_search)"
            )
        )
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_audit_search_workspace "
                "ON audit_search_index (workspace_id, axis)"
            )
        )
    for axis in _PG_AXES:
        spec = _PG_TRIGGER_SPECS[axis]
        session.execute(text(_pg_upsert_function_sql(axis, spec)))
        session.execute(text(_pg_delete_function_sql(axis, spec)))
        for stmt in _pg_attach_trigger_sql(axis, spec):
            session.execute(text(stmt))
    if not table_already_existed:
        for axis in _PG_AXES:
            session.execute(text(_PG_INITIAL_POPULATE_SQL[axis]))
    session.commit()
    return not table_already_existed


def rebuild_index(session: Session, counts: dict[str, int]) -> dict[str, int]:
    """Drop and re-seed the PG FTS index from the source tables."""
    session.execute(text("DELETE FROM audit_search_index"))
    for axis in _PG_AXES:
        session.execute(text(_PG_INITIAL_POPULATE_SQL[axis]))
    for axis_name in counts:
        count_value = (
            session.execute(
                text("SELECT COUNT(*) FROM audit_search_index WHERE axis = :axis"),
                {"axis": axis_name},
            ).scalar()
            or 0
        )
        counts[axis_name] = int(count_value)
    session.commit()
    return counts
