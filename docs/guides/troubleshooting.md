# Troubleshooting

Symptom-first index. If a known landmine has been documented in
a `BUG-NN-NN` source comment, that's referenced too.

## Install + first boot

### `docker: pull access denied` / `manifest unknown` for `ghcr.io/flohofstetter/...`

The pinned tag doesn't exist. Drop `PQL_VERSION` / `SOYUZ_VERSION`
to use the compose defaults, or check the published tags on the
repo's GHCR packages page. The packages are public — no
`docker login` is needed.

### `docker compose -f … -f docker-compose.dev.yml build` fails on the soyuz build context

The contributor build override needs a sibling `../soyuz-catalog`
checkout:

```bash
git clone https://github.com/FloHofstetter/soyuz-catalog.git ../soyuz-catalog
```

Or drop the `-f docker-compose.dev.yml` override to pull the
published image instead of building.

### `http://127.0.0.1:8000` returns 404 for everything immediately

PointlesSQL booted before Alembic finished. Wait ~10 s and
retry. `docker compose logs pointlessql` should show
`Alembic: upgraded head`.

### `docker compose up` says `soyuz-catalog healthcheck: unhealthy`

soyuz-catalog image failed to start. Check
`docker compose logs soyuz-catalog`. Most common: stale SQLite
in `/app/data` from a previous version.

```bash
docker compose down -v # -v wipes the named volumes
docker compose up -d
```

## Auth + sessions

### Can't log in immediately after restart

The JWT signing key changed (`POINTLESSQL_AUTH_SECRET_KEY` env
or default flipped). Old session cookies are invalid. Either
re-login or set `POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS` to the
old value during a 7-day grace period.

See [Auth → key rotation](../concepts/auth.md).

### Bearer token returns 401 even though it was valid yesterday

Either the key was revoked (`/admin/api-keys` → check
`revoked_at` column) or its `expires_at` passed. Mint a new one
with `pointlessql admin issue-auditor-key`.

### Cookie session and Bearer header both present → audit row says cookie principal, not the API-key name

Expected. Cookie wins; the Bearer header is ignored when both
are present. Strip the `Authorization` header in the request
that should attribute to the API key.

## Plugin / Hermes

### Plugin tool list is empty

`POINTLESSQL_BASE_URL` or `POINTLESSQL_API_KEY` not set in
`~/.hermes/.env`. After fixing, restart Hermes.

### `pql_promote_model` is missing from the tool list

`POINTLESSQL_SUPERVISOR_MODE=1` not set. Family B tools are
gated at registration time — see
[Permissions → Plugin-side gating](../reference/permissions.md#plugin-side-gating).

### Audit-Reviewer fires but writes no review

Wake-gate printed `wakeAgent: false`. That's the expected
optimisation on all-`ok` days. Force-fire by passing
`--ignore-wake-gate` to `hermes cron tick`.

### Tool calls succeed but no audit rows appear

The agent run id isn't being stamped onto the operations.
Confirm `POINTLESSQL_AGENT_RUN_ID` is set in the agent's session
env — Hermes plugin's `lifecycle.pre_llm_call` sets it per turn.
A bare REPL inherits whatever the parent process had.

### `ToolUseError: 34x args={} loop against pql_list_schemas`

The LLM is repeatedly calling a required-args tool with no args.
Known limitation of `kimi-k2.6` — switch to
`claude-haiku-4-5` or `claude-opus-4-7`.

## PQL writes

### `pql.write_table()` raises `OutsideAgentRunContext`

Called outside any agent run. Either set
`POINTLESSQL_AGENT_RUN_ID` before the call or use the explicit
context manager:

```python
with PQL().agent_run(name="adhoc") as pql:
 pql.write_table(...)
```

### `pql.merge()` raises `BranchPromotionConflictError`

Two branches mutated the same row. Pointer-swap can't merge
implicitly — pick a winner and re-merge manually.

See [ADR-0003 Delta-branching](../decisions/0003-delta-branching-spike.md).

### `pql.rollback()` raises `RollbackError: table has been written since`

 fail-loud: the table's current Delta version no longer
matches the op-row's `delta_version_after`. Rolling back would
overwrite newer data. Either skip the rollback or first roll
back the newer ops too (in reverse order).

### Source-tree links break after refactor

Walkthroughs intentionally point at `../../pointlessql/...` from
`docs/e2e-walkthroughs/`. When mkdocs builds with `--strict`
those links warn — they're not in `docs/`. has the
cross-link sweep that fixes this; until then `mkdocs build`
prints ~117 warnings that are not bugs.

## Audit cockpit

### Anomaly verdicts are all `ok` even though things are clearly wrong

The σ baseline window may be too long. Drop
`POINTLESSQL_AUDIT_ANOMALY_BASELINE_WINDOW_DAYS` from `7` to
`3` for tighter sensitivity. See
[Configuration → Audit](../reference/configuration.md#audit).

### Value-changes column is masked everywhere

Default `POINTLESSQL_AUDIT_PII_MODE=hash_only`. Set to
`store_clear` only in single-tenant deployments where every
viewer is trusted. See
[PII modes](../concepts/pii-modes.md).

### Grafana panel shows `cost_est` as `NaN`

 known issue: `cost_est` is `Decimal` and the
SQLite-datasource plugin can't render it directly. The shipped
dashboard JSON wraps every reference in `CAST(... AS REAL)`.
Custom panels need the same cast.

## Notebooks

### Notebook autosave triggers a server reload

Pre- bug. Fixed: `uvicorn --reload` now pins the
watch dirs to the source tree only (BUG-64-03 in
`pointlessql/api/main.py`). If you still see this, you're on a
earlier build.

### `BootstrapModalNotShowing` after Alpine update

Don't use `x-show` on `.modal` — Alpine 3.14 strips inline
`display:block` and `.modal { display: none }` wins on the
false→true transition. Use `:class="{ 'd-block': flag }"`
instead (BUG-67-01).

### Cell parser crashes on a `.py` notebook from another editor

 made the marker grammar **IDE-agnostic** (UUID-free,
content-hash identity). If you get a crash, the file may be
from a -era editor. Re-save once in the new editor
and the markers normalise.

See ADR-0001 [Notebook editor](../decisions/0001-notebook-editor.md).

## Storage / Delta

### Delta CDF read returns empty after a merge

`track_value_changes=True` opt-in. Without it,
`lineage_value_changes` stays empty even if the merge mutated
columns.

### `BranchPromotionConflictError` after a clean merge

The conflict-detection considered upstream-side commits since
the branch was created — it doesn't model the merge as a
three-way join. Promote first, *then* merge upstream.

### `_lineage_row_id` column appears in user-facing queries

It's a synthetic column auto-added on bronze writes.
Filter it out in your `SELECT` lists, or use
`pql.table(...).drop(columns=["_lineage_row_id"])` after read.

## CI / packaging

### `gh secret set --body -` set the literal dash, not stdin

Known landmine: `--body -` is **not** stdin. Omit `--body`:

```bash
echo "$SECRET" | gh secret set NAME
```

### `mkdocs build` fails on `pointlessql.services.audit_stream not found`

`audit_stream` isn't a top-level module — its writers are
embedded in individual `*_routes.py` and `services/audit.py`.
 fixed the docs reference to point at the actual
modules; if you wrote a new mkdocstrings directive, double-check
the dotted path.

### CI `pytest` is green but `alembic check` is red

ORM ↔ migration drift. `alembic check` compares ORM ↔
*generated* migration, not ORM ↔ deployed DB. Fix in models,
not in a new migration. See the
[Sprint Q.5 quality sweep](https://github.com/FloHofstetter/PointlesSQL/blob/main/CHANGELOG.md)
and the alembic-check-blind-spot feedback note for the full
context.

## Where to read next

- [FAQ](faq.md) — non-error questions
- [Operator cookbook](operator-cookbook.md) — what to do
 proactively
- [Configuration reference](../reference/configuration.md) —
 every env var that gates behaviour
- The walkthroughs each have their own **Failure modes** block
 for the per-surface error envelopes
