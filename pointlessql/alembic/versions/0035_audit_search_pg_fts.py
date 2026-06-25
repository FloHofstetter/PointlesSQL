"""audit_search_index Postgres FTS via tsvector + GIN

The Phase-18.7 migration ``y5u7v9w1x3z5`` shipped a SQLite FTS5
virtual table; Postgres deployments skipped it and the cockpit
search returned ``available=false``.  Sprint 30.1 closes that
cliff with a Postgres-native equivalent: a single
``audit_search_index`` table plus a GIN index on a generated
``tsvector`` column, fed by five PL/pgSQL trigger functions
(one per source table — ``agent_runs``, ``agent_run_operations``,
``query_history``, ``agent_run_tool_calls``, ``audit_log``).

Layout mirrors the SQLite schema deliberately so the service
layer in :mod:`pointlessql.services.audit_fts` can dispatch on
dialect and keep the same rowshape: ``(axis, entity_id, run_id,
principal, table_fqn, workspace_id, snippet, rank)``.

SQLite deployments skip this migration — the SQLite FTS5
virtual table from ``y5u7v9w1x3z5`` is the system of record there.

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-05 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_AXES: tuple[str, ...] = ("runs", "ops", "queries", "tool_calls", "audit_log")


_TRIGGER_FUNCTIONS: dict[str, dict[str, str]] = {
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


_INITIAL_POPULATE_SQL: dict[str, str] = {
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


def _trigger_function_sql(axis: str, spec: dict[str, str]) -> str:
    """Build the upsert PL/pgSQL function for a single axis."""
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


def _trigger_delete_function_sql(axis: str, spec: dict[str, str]) -> str:
    """Build the delete PL/pgSQL function for a single axis."""
    return f"""
CREATE OR REPLACE FUNCTION audit_search_{axis}_delete() RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM audit_search_index
        WHERE axis = '{axis}' AND entity_id = OLD.{spec["entity_col"]}::text;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
"""


def _trigger_attach_sql(axis: str, spec: dict[str, str]) -> list[str]:
    """Build the CREATE TRIGGER statements that bind the functions."""
    table = spec["table"]
    return [
        f"DROP TRIGGER IF EXISTS audit_search_{axis}_aiu ON {table};",
        f"DROP TRIGGER IF EXISTS audit_search_{axis}_ad ON {table};",
        (
            f"CREATE TRIGGER audit_search_{axis}_aiu "
            f"AFTER INSERT OR UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION audit_search_{axis}_upsert();"
        ),
        (
            f"CREATE TRIGGER audit_search_{axis}_ad "
            f"AFTER DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION audit_search_{axis}_delete();"
        ),
    ]


def upgrade() -> None:
    """Create the PG audit_search_index table + 5 trigger sets.

    Skips entirely on non-PG dialects: SQLite uses the FTS5 virtual
    table from migration ``y5u7v9w1x3z5`` instead.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Pre-replace ``.`` / ``_`` / ``-`` / ``@`` with spaces in the
    # GENERATED tsvector so PG's ``simple`` parser splits UC FQNs
    # and emails into separate tokens, matching the SQLite FTS5
    # ``unicode61 separators '._-'`` tokenizer behaviour.  Without
    # this, ``alice@example.com`` would tokenize as one email
    # token on PG but as three tokens on SQLite, breaking
    # cross-dialect parity.
    bind.execute(
        text(
            r"""
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
                        regexp_replace(COALESCE(text_corpus, ''),
                                       '[._@\-]+', ' ', 'g'))) STORED,
                PRIMARY KEY (axis, entity_id)
            );
            """
        )
    )
    bind.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_audit_search_text_search "
            "ON audit_search_index USING gin(text_search);"
        )
    )
    bind.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_audit_search_workspace "
            "ON audit_search_index (workspace_id, axis);"
        )
    )

    for axis in _AXES:
        spec = _TRIGGER_FUNCTIONS[axis]
        bind.execute(text(_trigger_function_sql(axis, spec)))
        bind.execute(text(_trigger_delete_function_sql(axis, spec)))
        for stmt in _trigger_attach_sql(axis, spec):
            bind.execute(text(stmt))

    for axis in _AXES:
        bind.execute(text(_INITIAL_POPULATE_SQL[axis]))


def downgrade() -> None:
    """Drop triggers, functions, and the table on Postgres."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for axis in _AXES:
        spec = _TRIGGER_FUNCTIONS[axis]
        table = spec["table"]
        bind.execute(text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_aiu ON {table};"))
        bind.execute(text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_ad ON {table};"))
        bind.execute(text(f"DROP FUNCTION IF EXISTS audit_search_{axis}_upsert();"))
        bind.execute(text(f"DROP FUNCTION IF EXISTS audit_search_{axis}_delete();"))

    bind.execute(text("DROP INDEX IF EXISTS ix_audit_search_workspace;"))
    bind.execute(text("DROP INDEX IF EXISTS ix_audit_search_text_search;"))
    bind.execute(text("DROP TABLE IF EXISTS audit_search_index;"))
