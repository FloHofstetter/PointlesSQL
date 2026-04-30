# Operator cookbook

Twenty short recipes for the things an operator does in a
typical week.  Each recipe is one to three sentences plus a
link to the long-form walkthrough for the deep version.

## Daily

### 1. Check yesterday's audit digest

Open <http://127.0.0.1:8000/admin/audit> → **Anomaly digest**
card.  All-`ok` ⇒ done.  Any `warn` / `critical` ⇒ click into
the per-axis view.

Walkthrough: [admin-audit.md](../e2e-walkthroughs/admin-audit.md).

### 2. Review the latest agent-review

Same page → **Latest review** card.  The daily Audit-Reviewer-
Bot's markdown digest from `agent_reviews`.  If it's empty, the
wake-gate skipped the LLM (expected on `ok` days).

Walkthrough: [audit-reviewer-daily.md](../e2e-walkthroughs/audit-reviewer-daily.md).

### 3. Drill into a suspicious run

Run-search → click run → **Operations** tab → look for
`error_message`-populated rows.  **Lineage** tab → walk back
through `lineage_row_edges` to the input rows.

Walkthrough: [admin-audit.md](../e2e-walkthroughs/admin-audit.md).

## Weekly

### 4. Review the four sub-tab outputs

Each top-level tab on the Audit Cockpit has its own time-series.
A weekly skim of the trend lines catches drift before it
becomes an anomaly.

### 5. Audit your audit-sinks

`/admin/audit-sinks` → confirm webhooks are firing (`last_fire_at`
is recent for active sinks).  Re-test any sink showing
`last_error_at`.

Walkthrough: [audit-sinks.md](../e2e-walkthroughs/audit-sinks.md).

### 6. Sweep the orphaned branches

`/admin/branches` → look for `status=active` branches older than
7 days that aren't tied to an active run.  Discard or promote.

Walkthrough: [branches.md](../e2e-walkthroughs/branches.md).

### 7. Check disk pressure

If branching is in heavy use, the deep-copy cloud strategy
inflates storage cost.  Check the Grafana dashboard's storage
panel (when [the overlay is up](../e2e-walkthroughs/dashboards.md))
or the host's `df -h`.

## Per-agent-bring-up

### 8. Mint a new API key

```bash
pointlessql admin issue-auditor-key --name <name> [--supervisor]
```

Walkthrough: [CLI reference](../reference/cli.md#pointlessql-admin-issue-auditor-key).

### 9. Revoke a leaked key

`/admin/api-keys` → find the row → **Revoke**.  Sets
`revoked_at`; subsequent requests with the token return 401
immediately.

### 10. Pre-flight a new agent

Read the [agent bring-up recipe](agent-bring-up.md) and run
through steps 1-5 in a sandbox before pointing the agent at
production data.

## Per-incident

### 11. Roll back yesterday's bad ETL

Find the run → **Rollback preview** → confirm the version diff
→ admin-only **Execute rollback**.  Emits
`pointlessql.rollback.executed` CloudEvent.

Walkthrough: [rollback.md](../e2e-walkthroughs/rollback.md).

### 12. Triage "what broke this run?"

Wake the Incident-Responder bot via Slack DM with the run id.
Multi-turn drill-down: failing op → rejects → external writes →
contributing agent.

Walkthrough: [incident-responder.md](../e2e-walkthroughs/incident-responder.md).

### 13. Detect external writes

`/admin/external-writes` → look for `unattributed_writes` rows
without a matching `agent_run_id`.  Either an agent skipped the
audit path (bug) or a third-party process wrote directly (policy
violation).

Walkthrough: [admin-audit.md](../e2e-walkthroughs/admin-audit.md).

## Per-model

### 14. Promote a model to champion

Browse to `/models/<full_name>` → **Promotion** tab → pick the
target version → enter a **reason** → click **Promote**.
Supervisor-scoped.  Emits `pointlessql.model.promoted`
CloudEvent.

Walkthrough: [models-promotion.md](../e2e-walkthroughs/models-promotion.md).

### 15. Trace inference back to training

`/models/<full_name>` → **Lineage** tab → bidirectional DAG with
`trained_from` (source tables) and `inferred_to` (prediction
tables) edges.

Walkthrough: [inference-lineage.md](../e2e-walkthroughs/inference-lineage.md).

### 16. Compare two model versions

`/models/<full_name>/versions/<n>` → click **Compare against
champion** (or any other version).  Side-by-side metric +
hyperparameter diff.

Walkthrough: [models-tab.md](../e2e-walkthroughs/models-tab.md).

## Per-data-issue

### 17. Time-travel to before a bad write

Admin only.  `/api/lineage/row-at-version?table=...&row_id=...&version=N`
or via the UI's table-detail **History** tab.

Walkthrough: [time-travel.md](../e2e-walkthroughs/time-travel.md).

### 18. Investigate a row's value history

Auditor only.  Run-detail → click any row → **Value-changes
trace**.  Shows the before/after for every column at every
merge.

Walkthrough: [admin-audit.md](../e2e-walkthroughs/admin-audit.md).

### 19. Find rejected rows from a merge

Run-detail → **Rejects** tab.  Source rows that failed the merge
condition (type mismatch, missing key) with the rejection
reason.

Walkthrough: [admin-audit.md](../e2e-walkthroughs/admin-audit.md).

## Maintenance

### 20. Bump the soyuz-catalog pin

When soyuz ships an `rcN+1` tag, edit `pyproject.toml`'s
`[tool.uv.sources] soyuz-catalog-client` block, run `uv sync`,
test, commit.  See
[`CLAUDE.md → Wiring soyuz-catalog`](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md).

For development that needs an editable sibling checkout, swap
with `bash scripts/use-editable-soyuz.sh` and back with
`bash scripts/use-pinned-soyuz.sh`.

## Where to read next

- [Agent bring-up](agent-bring-up.md) — full recipe for adding a
  new agent to the loop
- [Troubleshooting](troubleshooting.md) — when things go wrong
- [FAQ](faq.md) — questions you might still have
- [E2E walkthroughs index](index.md#e2e-walkthroughs) — every
  surface in deterministic-replay form
