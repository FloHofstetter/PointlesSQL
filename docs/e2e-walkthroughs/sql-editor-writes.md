# SQL editor — write statements (Phase 63)

> **Mode:** `browser` · **Phase:** 63 · **Surface:** /sql write traffic + audit linkage

Exercises the Phase-63 dispatcher that turned the SELECT-only
editor into an AST-classifying frontend over typed primitives.
Walks INSERT FROM SELECT, CREATE TABLE AS SELECT, UPDATE,
DELETE, DROP TABLE, CREATE / DROP SCHEMA, MERGE, the
destructive-statement confirmation modal, the dispatcher's
ALTER TABLE deferral, the multi-statement batch route, and the
audit-trail wiring (every editor write lands an
`agent_run_operations` row + a `query_history` row with
`agent_run_id` populated, surfaced under
`/runs/<run_id>`).

## Preconditions

- [`auth.md`](auth.md) and [`catalog-browsing.md`](catalog-browsing.md)
  ran first. `admin@pql.test` is logged in.
- [`sql-editor.md`](sql-editor.md) ran first — it covers the
  baseline SELECT path which Phase 63 leaves untouched.
- `main.sales.orders` exists with at least 5 rows
  (`{id: 1..5, name: a..e, country: ['AT','DE','AT','DE','AT']}`).
- `main.bronze.staging` exists with the same schema, used as a
  source for INSERT / MERGE.

## Walkthrough

1. **INSERT INTO … SELECT lands an `agent_run` row.**
   - Action: open `/sql`. Type
     `INSERT INTO main.silver.copy SELECT id, name FROM main.sales.orders`
     and press `Cmd/Ctrl+Enter`.
   - Assert: the result card no longer shows a rows-table — it
     shows the new "DML" badge (blue), the target FQN
     `main.silver.copy`, the rows-affected count, and a
     "View op trace" button.
   - Assert (server-side): the response JSON has
     `{kind: 'dml', op_name: 'write_table', target,
       rows_affected, agent_run_id}`. `query_history.agent_run_id`
     for this row is populated (visible at
     `/queries?read_kind=sql_dml`).

2. **`View op trace` deep-links to the editor's run row.**
   - Action: click "View op trace" in the result card.
   - Assert: navigates to `/runs/<run_id>`. The run-detail
     page shows `agent_id='sql-editor'`, the originating
     SQL in the query-history panel, and one
     `agent_run_operations` row with `op_name='write_table'`
     pointing at `main.silver.copy`.

3. **UPDATE is dispatched through `pql.update`.**
   - Action: back to `/sql`. Type
     `UPDATE main.silver.copy SET name = 'updated' WHERE country = 'AT'`
     and run.
   - Assert: result card shows the "UPDATE" badge,
     `rows_affected = 3`. `View op trace` opens a fresh
     run with op `update`, target `main.silver.copy`, and
     `params_json` carrying the `set_columns` + `where`.

4. **DELETE without WHERE triggers the destructive-confirm modal.**
   - Action: type `DELETE FROM main.silver.copy` (no WHERE),
     press `Cmd/Ctrl+Enter`.
   - Assert: a browser `confirm()` modal pops up: "This
     DELETE has no WHERE clause and will remove every row in
     the target. Confirm?". Click "Cancel" → no request fires,
     editor returns to ready state.

5. **DELETE with WHERE clause runs without confirmation.**
   - Action: edit to
     `DELETE FROM main.silver.copy WHERE country = 'AT'` and
     run.
   - Assert: no modal. Result card shows the "DELETE" badge
     (yellow), `target=main.silver.copy`. Re-running
     `SELECT count(*) FROM main.silver.copy` returns the
     remaining row count.

6. **DROP TABLE triggers the destructive-confirm modal.**
   - Action: type `DROP TABLE main.silver.copy` and run.
   - Assert: modal appears — "This statement will permanently
     remove a UC object. Confirm?". Click OK.
   - Assert: result card shows the "DROP TABLE" badge (red),
     and the soyuz row is gone (visible by refreshing the
     catalog tree). The Delta files on disk stay (Hive-style
     external-table semantics, documented in the result
     hint).

7. **CREATE SCHEMA / DROP SCHEMA require admin.**
   - Action: as admin, run `CREATE SCHEMA main.bronze`. Then
     `DROP SCHEMA main.bronze CASCADE`.
   - Assert: both succeed. Result card kind is `ddl`,
     op_name `create_schema` / `drop_schema`.
   - Action: log in as `user@pql.test` (non-admin), retry
     `CREATE SCHEMA main.bronze`.
   - Assert: 403 with "admin role required".

8. **CREATE TABLE AS SELECT bootstraps a new target.**
   - Action: as admin, run
     `CREATE TABLE main.silver.copy2 AS SELECT * FROM main.sales.orders`.
   - Assert: result card shows "CREATE TABLE AS" badge,
     `rows_affected = 5`. Refreshing the catalog tree shows
     the new table.

9. **Bare CREATE TABLE rejects with a hint to the table-detail UI.**
   - Action: run `CREATE TABLE main.silver.foo (a INT, b TEXT)`.
   - Assert: 400 / `sql_execution_error` with the message
     "Bare CREATE TABLE … use the table-detail UI's New Table
     form."

10. **MERGE upsert path translates and lands as `pql.merge`.**
    - Action: run
      `MERGE INTO main.silver.copy2 t USING main.bronze.staging s
       ON t.id = s.id
       WHEN MATCHED THEN UPDATE SET name = s.name
       WHEN NOT MATCHED THEN INSERT (id, name) VALUES (s.id, s.name)`.
    - Assert: result card shows "MERGE" badge with insert /
      update counts. The agent_run row's
      `agent_run_operations` table has one row with
      `op_name='merge'`.

11. **MERGE WHEN MATCHED THEN DELETE rejects cleanly.**
    - Action: run a MERGE that includes
      `WHEN MATCHED THEN DELETE`.
    - Assert: 400 with
      "WHEN MATCHED branch must be `THEN UPDATE`. WHEN MATCHED
      THEN DELETE is not supported." Pointer at
      `POST /api/pql/merge` for elaborate cases.

12. **ALTER TABLE returns the deferred-feature message.**
    - Action: run
      `ALTER TABLE main.silver.copy2 SET TBLPROPERTIES("comment" = "x")`.
    - Assert: 400 with "ALTER TABLE is not yet supported from
      the SQL editor. Use the table-detail UI's edit form …".

13. **EXPLAIN restricted to SELECT.**
    - Action: with the editor pre-filled with
      `DROP TABLE main.silver.copy2`, click "Explain".
    - Assert: 400 with "EXPLAIN is only supported for SELECT
      statements."

14. **Multi-statement batch route runs `;`-separated SQL.**
    - Action: from a shell, POST
      `{"sql": "SELECT 1; SELECT 2;"}` to
      `/api/sql/execute_batch`.
    - Assert: 200 with
      `{n_statements: 2, failed_index: null, results: [...]}`.
      Each result entry has `kind='select'` and the row body.
    - Action: POST with `atomic=true` and a SQL that
      includes a write that succeeds followed by a write
      that fails (e.g. UPDATE on a missing table).
    - Assert: response carries `failed_index = 1` and the
      `rollback` field lists the prior write op that was
      undone via `pql.rollback` (Phase 16).

15. **CREATE / DROP CATALOG rejected at parse time.**
    - Action: run `CREATE CATALOG hive`.
    - Assert: 400 with "Unsupported statement type: Command"
      — sqlglot parses CATALOG DDL as `exp.Command` with no
      structured args. The admin UI is the supported path
      for catalog management.

16. **Audit trail surface check on `/runs/`.**
    - Action: navigate to `/runs/?agent_id=sql-editor`.
    - Assert: the runs list shows every editor write from
      this walkthrough, with `agent_id='sql-editor'`,
      target FQN in `tables_touched`, and the originating
      SQL preview accessible via the run-detail page.

## Verification

- The editor's SELECT path is unchanged: rows table renders,
  no `agent_run` row created.
- Every write statement creates exactly one `agent_run` row
  + one `agent_run_operations` row (DML primitives) or a
  direct op row (DDL via soyuz).
- `query_history.agent_run_id` is populated for every editor
  write.
- The destructive-confirm modal fires exactly twice in this
  walkthrough (step 4 and step 6).
- The `View op trace` deep-link works for every DML/DDL write.
- Phase-14 external-write scanner does NOT flag any of the
  Phase-63 writes as unattributed (per
  [project_phase63_closed.md](../../../.claude/projects/-home-flo-git-PointlesSQL/memory/project_phase63_closed.md)).
