---
title: "Cluster 07 — Phase 18–20 Audit Cockpit (dev-log)"
audience: contributor
cluster_id: "07"
phases: "18-20"
closed: "2026-04-29"
---

# Cluster 07 — Phase 18–20 Audit Cockpit (dev-log)

> Phase 18 (Audit Cockpit), Phase 19 (Audit-Reviewer Agent + Grafana), Phase 20 (Forensics + Retention).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 18.6+ closed (2026-05-05)** — four sub-sprints landed
  (18.6 inbox + run-list badge, 18.7 audit-FTS, 18.8 runs-by-table
  reverse index, 18.9 cell + column-lineage diff).  Sprint 18.10
  (anomaly-verdict cache) deferred per plan: contingent on a
  real ≥10⁴-run lake breaching ``/audit/inbox`` p95 > 2s.
  Today's instances stay sub-100ms on the live aggregator.

> from CHANGELOG.md (bucket: **Closed**)

### Closed — Phase 20: Forensics + Retention (2026-04-29)

Five sub-sprints landed in one autonomous session, closing the
"forensics + retention" governance pass that the post-Phase-15.7
strategy-conversation flagged as the orthogonal gap to the
already-shipped audit capture / display / query stack.

What's now in place:

- **Audit-stream forwarder** (Sprint 20.0). Six governance event
  types (`external_write.detected`, `cost_gate.denied`,
  `audit_export.issued`, `policy.violated`, `lineage.pruned`,
  `audit_sink.test`) fan out to admin-configured sinks of three
  types — webhook (HMAC), S3 (SigV4 PUT, supports
  MinIO/Cloudflare R2 via `endpoint_url`), AWS CloudTrail
  (PutAuditEvents).  Off by default; admin CRUD at
  `/api/admin/audit-sinks`.
- **Write-time PII redaction** (Sprint 20.1). `pii_mode` defaults
  to `hash_only`: any column whose name matches a built-in PII
  pattern (`email`, `phone`, `ssn`, `credit_card`, `iban`,
  `passport`, `first_name`, `address`, `birth`, +
  contains-`pii`) gets HMAC-SHA256-hashed at `record_value_changes`
  time.  `system_keys` table holds the auto-generated 32-byte
  secret.  `redact_with_audit_log` mode also appends one
  `audit_log` row per masked per-op call.
- **Lineage retention** (Sprint 20.2). Per-axis TTLs on the four
  lineage tables (defaults: row_edges 365, row_rejects 365,
  value_changes 730, column_map none).  Lifespan task ticks every
  24h; each prune appends an `audit_log` row + fires a
  `pointlessql.lineage.pruned` governance CloudEvent.
- **Time-travel value queries in UI** (Sprint 20.3).
  `pql.table_at_version` / `pql.table_at_timestamp`; routes
  `/api/tables/{fqn}/versions`,
  `/api/tables/{fqn}/preview-at-version`,
  `/api/lineage/row-at-version` (admin-gated); table-detail
  preview "View at:" select; row-trace admin-only version-input
  card.  `query_history.read_kind` enum extends with
  `pql_table_at_version`.
- **Cross-tool lineage facet ingest** (Sprint 20.4). PointlesSQL
  emits `columnLineage` + `valueChange` facets (the latter is a
  PointlesSQL extension, namespaced under `_producer`); soyuz
  ingests both via two new ORM models (`LineageColumnEdge`,
  `LineageValueChange`), Alembic `016`, expanded `ingest_event`
  walker, response counters
  (`accepted_column_edges`, `accepted_value_changes`).  PII
  values cross the wire pre-redacted.

Numbers:

- 5 commits on PointlesSQL: `1072170`, `b715f3f`, `ca07013`,
  `f06ba97`, `8050c2f` + this closing commit.
- 1 commit on soyuz-catalog: `2d73c87` (locally tagged
  `v0.2.0rc4`, push pending).
- 7 new tables / migrations across both repos
  (`audit_sinks`, `governance_events`, `system_keys`,
  `lineage_column_edges`, `lineage_value_changes` +
  PointlesSQL Alembic `m3h4i5j6k7l8` / `n4i5j6k7l8m9` +
  soyuz Alembic `016`).
- 3 new admin/operational walkthroughs
  (`docs/e2e-walkthroughs/audit-sinks.md`,
  `docs/e2e-walkthroughs/time-travel.md`,
  `docs/audit/pii-modes.md`).
- ~40 new public API surface points (admin CRUD + per-event-
  type emission helpers + 3 time-travel routes).

What's deliberately out of scope:

- Admin HTML page for audit-sinks — JSON-only routes shipped;
  page is a Phase-20.6+ follow-up.
- Soyuz tag-driven PII detection at write time — would dominate
  per-write cost; the Phase-18 render-time masking still gates
  tagged-but-non-pattern columns at the API surface.
- Foreign-producer `valueChange` schema validation — soyuz
  documents the facet as PointlesSQL-defined and ingests
  permissively.
- Pushing the `v0.2.0rc3` / `v0.2.0rc4` soyuz tags — same
  posture as the Phase-14 push that's still pending; install
  works because both response-shape extensions are additive.

### Added — Sprint 20.4: Soyuz columnLineage + valueChange (2026-04-29)

Cross-tool sibling to the PointlesSQL-only column / value lineage
stack.  Two OpenLineage facets now flow from PointlesSQL emission
into soyuz-side persistence:

- `services/soyuz_lineage.emit_event_sync` accepts optional
  `column_edges` + `value_changes` lists.  Builds
  `outputs[*].facets.columnLineage` (spec 1.x) and
  `outputs[*].facets.valueChange` (PointlesSQL extension under
  `_producer = "https://github.com/FloHofstetter/pointlessql"`).
- `operations._emit_lineage_after_commit` threads the recorder's
  `pending_column_edges` + `pending_value_changes` through so every
  merge / declarative write that already populates
  `LineageColumnMap` + `LineageValueChange` (Phases 15.6 + 15.7)
  automatically surfaces in soyuz too.
- PII safety: PointlesSQL emits **already-redacted** values when
  `pii_mode != store_clear` (Sprint 20.1's default `hash_only`
  rewrites `old_value` / `new_value` to a 16-hex HMAC), so soyuz
  never sees cleartext.

Soyuz changes (commit pending push, locally tagged `v0.2.0rc4`):
two new ORM models (`LineageColumnEdge`, `LineageValueChange`),
Alembic `016`, `ingest_event` facet walker, response counters
(`accepted_column_edges`, `accepted_value_changes`).  See
`../soyuz-catalog/CHANGELOG.md` for the full soyuz-side notes.

### Added — Sprint 20.3: Time-travel value queries in UI (2026-04-29)

Surfaces the version arithmetic
`agent_run_operations.delta_version_after` already captures.

- New `pql.table_at_version(fqn, n)` + `pql.table_at_timestamp`
  helpers wrap `DeltaTable.load_as_version`.  Each call writes a
  `query_history` row with `read_kind="pql_table_at_version"`.
- New `api/time_travel_routes.py` exposes three read-only routes:
  `GET /api/tables/{fqn}/versions` (history joined with
  `agent_run_operations` so each version names the originating
  run when known), `GET /api/tables/{fqn}/preview-at-version`
  (paged rows up to 200), `GET /api/lineage/row-at-version`
  (admin-gated single-row lookup keyed on `_lineage_row_id`).
- Table-detail preview card gains a "View at:" select.
  Row-trace page gains an admin-only "View this row at version"
  card.  Both consume the new API.
- `query_history.read_kind` enum extends with
  `pql_table_at_version` so `/queries` surfaces time-travel reads
  alongside ordinary `pql.table()` calls.
- Browser-replay playbook in `docs/e2e-walkthroughs/time-travel.md`.

### Added — Sprint 20.2: Lineage retention TTLs (2026-04-29)

Bounded-growth invariant on the four lineage tables.  Each axis
gets its own retention threshold; the pruner runs as a lifespan
task next to the existing audit-cleanup loop.

- New `services/lineage_pruner.py`: `prune_once` (sync DB I/O) +
  `prune_once_async` (async wrapper that fires one
  `pointlessql.lineage.pruned` governance CloudEvent per axis
  after the DB commit).  Each per-axis prune appends an
  `audit_log` row (`actor_role=system`, `action=lineage_prune`,
  `target=lineage_<axis>`, `detail={deleted, cutoff,
  threshold_days}`).
- `LineageRetentionSettings` (env prefix
  `POINTLESSQL_AUDIT_LINEAGE_RETENTION_*`) with per-axis
  `*_days` thresholds.  `None` / `0` skips the axis.  Defaults:
  row_edges 365, row_rejects 365, value_changes 730,
  column_map `None`.
- `_lineage_pruner_loop` lifespan task ticks every
  `audit.cleanup_interval_seconds` (default 24h).  Active only
  when at least one axis has a positive threshold.
- Sprint 20.0's `EVENT_TYPE_LINEAGE_PRUNED` finds its first
  emitter.  Audit-stream sinks see prunes alongside external-
  write detections and cost-gate denials.

### Added — Sprint 20.1: PII detection + masking write-hook (2026-04-29)

Sprint 20.1 closes the cleartext-at-rest gap on
`lineage_value_changes`.  Render-time masking from Phase 18.2 only
protected the API surface; this sprint rewrites the row before it
hits SQLite when `pii_mode` is anything other than `store_clear`.

- New `system_keys` table (Alembic `n4i5j6k7l8m9`) for the lazy
  install-scoped PII hash secret.  First-write generates a
  32-byte URL-safe random token.
- `services/pii_redactor.py` ships pattern-based PII detection
  (regex over column names — covers `email`, `phone`, `ssn`,
  `credit_card`, `iban`, `passport`, `first_name`, `last_name`,
  `address`, `birth`, plus generic `pii` substring), HMAC-SHA256
  hashing (16 hex chars, equality-joinable), and the literal
  `<redacted>` placeholder.
- `record_value_changes` accepts `pii_mode` + `pii_hash_secret`
  parameters.  `store_clear` keeps pre-20.1 behaviour;
  `hash_only` (the new default) rewrites old/new values to a
  16-hex HMAC for any pattern-matched column;
  `redact_with_audit_log` substitutes the literal `<redacted>`
  and appends one `audit_log` row per masked per-op call.
- `operations._record_value_changes_after_commit` resolves
  `Settings` and forwards the mode + secret automatically;
  primitives stay agnostic.
- Soyuz tag-driven PII detection stays out of the sync write path
  (would dominate per-write cost).  The Phase-18 render-time
  masking still gates tagged-but-non-pattern columns at the API.
- `docs/audit/pii-modes.md` documents the three modes, secret
  bootstrap, migration impact, and the verification recipe.
- Existing `lineage_value_changes` rows are NOT rewritten — soft
  transition.  Historical cleartext stays readable to admins via
  render-time masking; new writes hash.

### Added — Sprint 20.0: Audit-Stream forwarder (2026-04-29)

Phase 20 opens with the audit-stream forwarder: a settings-driven,
plug-in-typed CloudEvents fan-out that mirrors the existing webhook
dispatcher's HMAC + retry contract for new sink types.

- New `audit_sinks` table (id, name, type, config_json,
  is_active, event_types_json, created_at) plus FK-free
  `governance_events` table for non-run-scoped CloudEvents.
  Alembic `m3h4i5j6k7l8`.
- Three sink types ship: `webhook` (reuses the saved-query alert
  dispatcher), `s3` (httpx + minimal SigV4 signer at
  `services/aws_sigv4.py`, works against MinIO / R2 by setting
  `endpoint_url`), `aws_cloudtrail` (PutAuditEvents to the
  CloudTrail Data Service). SigV4 implementation verified against
  the AWS reference test vector.
- Five governance event types fire from the existing audit
  surfaces: `pointlessql.external_write.detected` (scanner),
  `cost_gate.denied` (`/api/sql/explain` when `needs_approval`
  flips true), `audit_export.issued` (`/admin/audit/export`),
  `policy.violated` (free hook for future), `lineage.pruned`
  (paired with Sprint 20.2). Run-lifecycle events stay on the
  Phase-13 `agent_run_events` path; admins flip
  `POINTLESSQL_AUDIT_STREAM_MIRROR_LIFECYCLE_TO_SINKS=1` to fan
  those into `audit_sinks` too.
- Admin CRUD at `/api/admin/audit-sinks` (GET/POST/PATCH/DELETE)
  with sensitive-key redaction on read-back, a `POST .../{id}/test`
  synthetic-envelope endpoint, and a `GET .../recent-events`
  tail of the last 50 governance rows.
- Off by default — `POINTLESSQL_AUDIT_STREAM_ENABLED=0`. The
  governance row always persists (durability matters); only the
  outbound POST is gated.
- Operational runbook in `docs/e2e-walkthroughs/audit-sinks.md`
  (curl-driven, no browser). Admin HTML page deferred to the
  Phase-20 close-memo bug-hunt sweep.

> from CHANGELOG.md (bucket: **Closed**)

### Closed — Phase 19: Audit-Reviewer Agent + Grafana (2026-04-29)

Six sub-sprints landed across two days, closing the original
"agents reviewing agents" thesis from the Phase-19 sketch.  The
audit lake captured by Phase 14-15 + the cockpit surface from
Phase 18 are now driven by three real personas, plus the Grafana
glance-trust dashboard that was Phase 19's quick-win opener.

Personas served:

- **Daily Audit-Reviewer-Agent** (Sprint 19.2.0/1/2) — Hermes cron
  at 06:00 UTC; wake-gate skips the LLM round-trip on clean days,
  on `warn`/`critical` the agent drafts Markdown, posts via
  `pql_post_audit_review` (PointlesSQL is the source of truth),
  PointlesSQL fans the CloudEvent out to admin-configured webhook
  destinations, Hermes also delivers via its own platform adapters.
  Cockpit "Latest review" card on `/` + `/agent-reviews/{id}`
  detail page.
- **Compliance-Bot** (Sprint 19.3) — read-only Hermes one-shot
  triggered by Slack/Matrix DM. Answers ad-hoc questions with the
  four-block Question/Answer/How/Caveats skeleton. Five hard
  prompt constraints (no writes, mandatory masking, no API-key
  echo, time-window pinning, refuse-and-escalate on remediation
  asks). New `/api/audit/principal-summary` route + matching
  plugin tool fill the runs-by-principal enumeration gap.
- **Incident-Responder** (Sprint 19.4) — multi-turn drill-down
  for "was hat Run X kaputt gemacht?". Takes a `run_id` up
  front, walks failing op → rejects → external-write neighbours.
  Pure prompt composition — no new server endpoints. Synthetic
  broken-run fixture (`scripts/seed-broken-run.py`) for replays.

Numbers:

- Plugin grew 29 → 32 tools (`pql_post_audit_review`,
  `pql_get_latest_review`, `pql_principal_summary`).
- Two new tables (`agent_reviews`, `review_destinations`,
  Alembic `l2g3a4b5c6d7`).
- Two new admin-gated CRUD routes for review destinations + four
  new auditor-gated agent-review routes (POST + latest + detail +
  principal-summary).
- One Hermes pre-run script (`scripts/audit-wake-gate.py`).
- Three new walkthroughs in `docs/e2e-walkthroughs/`
  (audit-reviewer-daily, compliance-bot, incident-responder)
  + three Hermes job manifests in `docs/hermes-jobs/`.
- Six commits (`57ec67c`, `8d6de75`, `fe5d26d`, `4735b76`,
  `51659b6`, plus the closing commit) against PointlesSQL; two
  commits (`ac57fed`, `14ad3ea`) against `hermes-plugin-pointlessql`.

What's deliberately out of scope:

- Conversation memory for the chat personas — that's Hermes' job;
  see the limitations sections in
  `docs/e2e-walkthroughs/{compliance-bot,incident-responder}.md`.
- "Auto-fix" / "draft remediation PR" personas. The read-only
  posture is the design intent — Sprint 19.5+ could add a
  write-shaped persona, but that's a different conversation.
- Per-job env overlays in Hermes. All cron jobs in an install
  share `~/.hermes/.env`; if you need separate keys per job, add
  Hermes-side feature support first.

### Added — Sprint 19.4: Incident-Responder persona (2026-04-29)

Third Phase-19 persona: multi-turn Hermes flow for "was hat Run X
kaputt gemacht?".  Takes a ``run_id`` up front (typically pasted from
a banner alert / deploy log), walks down to root cause across the
existing per-run audit axes, never recommends a write.

- **No new server endpoints.**  This sprint is purely prompt
  composition + a fixture: every tool the responder uses landed in
  Sprint 19.1.  The plugin tool-count is unchanged at 32.

- **System prompt + manifest** at
  ``docs/hermes-jobs/incident-responder.{md,json}``.  Three-block
  answer skeleton (Finding / Evidence / Next) optimised for
  follow-up questions.  Five hard constraints: stay focused on
  one run, never recommend a write, mention rollback as an option
  exactly once per conversation, surface external-write neighbours
  proactively, be terse (operator is on call).

- **Synthetic broken-run fixture** at
  ``scripts/seed-broken-run.py``.  Inserts one
  :class:`AgentRun` with status ``failed``, three
  :class:`AgentRunOperation` rows (``autoload`` ok / ``merge``
  errored on schema mismatch / ``write_table`` accumulated rejects),
  ~50 :class:`LineageRowReject` rows, and 2
  :class:`UnattributedWrite` rows landing in the same window.  Plus
  one extra ``succeeded`` run for the same principal so per-
  principal aggregations have a non-trivial denominator.  Prints
  the run_id for use in the chat prompt.

- **e2e walkthrough** at
  ``docs/e2e-walkthroughs/incident-responder.md`` exercises three
  drill-down patterns (failing op, op-3 rejects, proactive
  external-write callout) and four safety properties (refuses
  writes, rollback mentioned at most once, masking on
  value-changes, audit-of-audit history matches the tool surface).

### Added — Sprint 19.3: Compliance-Bot (ad-hoc Slack/chat persona) (2026-04-29)

Read-only Hermes one-shot flow that answers ad-hoc compliance
questions over the existing auditor toolset.  The persona name comes
from the original Phase-19 sketch: "welche Runs schrieben Q3 auf
PII-Spalten?" via Slack DM or slash-command.

- **New ``GET /api/audit/principal-summary``** (auditor-gated).
  Aggregates :class:`AgentRun` rows for one ``principal`` over a
  window and returns headline counters (runs, ops, rejects,
  value_changes, external_writes) plus the most recent ``limit``
  runs.  Closes the gap between Sprint 19.1's per-run audit axes and
  the persona's "enumerate runs by principal first" pattern.
  Self-tracks as ``read_kind='audit_api'`` like the rest of
  ``/api/audit/*``.

- **Plugin tool ``pql_principal_summary``.**  Required arg
  ``principal``; optional ``since`` / ``until`` / ``limit`` (1–200,
  server clamped).  Goes into ``register_auditor_tools`` so it loads
  only when ``POINTLESSQL_AUDITOR_MODE=1``.  Plugin grows from 31
  → 32 tools.

- **System prompt + manifest** at
  ``docs/hermes-jobs/compliance-bot.{md,json}``.  Four-block answer
  skeleton (Question / Answer / How / Caveats) so auditors can
  reproduce any answer from the tool-call trail.  Five hard
  constraints in the prompt: no writes, mandatory masking on
  value-changes, no API-key echo, mandatory time-window pinning,
  explicit refusal-and-escalation when the question would require a
  write.  Manifest uses Hermes' wake-on-message dispatch (no cron
  schedule); the chat-platform adapter routes incoming messages.

- **e2e walkthrough** at
  ``docs/e2e-walkthroughs/compliance-bot.md`` exercises the three
  canonical question shapes (runs-by-principal, yesterday's external
  writes, high-reject runs) and asserts the four safety properties:
  read-only refusal works, value-changes always masked, API-key never
  appears in output bytes, audit-of-audit history matches the
  observed tool surface.

### Added — Sprint 19.2.2: Wake-gate (skip clean days) (2026-04-29)

Optimisation pass on the daily Audit-Reviewer-Agent: most days have
nothing to report, and burning a full LLM round-trip on those days is
pointless and expensive.

- **`scripts/audit-wake-gate.py`.**  Hermes pre-run script invoked
  before the LLM call.  Hits `GET /api/audit/anomalies` for the three
  metrics (rejects, errored_ops, external_writes) against the
  closed-day window, prints a `#`-prefixed human-readable context
  block (the agent sees this as prompt context when it does wake),
  and emits the wake-gate JSON line as the FINAL non-empty stdout
  line.  On `ok` days the line is
  `{"wakeAgent": false, "severity": "ok"}` and Hermes skips the LLM
  round-trip per the contract in
  `hermes-agent/cron/scheduler.py:_parse_wake_gate`.  Failures
  (PointlesSQL unreachable, missing API key) fail open: the script
  always exits 0 and returns `{"wakeAgent": true}` so a transient
  outage never silences a real anomaly day.

- **Manifest update.**  `docs/hermes-jobs/audit-reviewer-daily.json`
  carries `"script": "scripts/audit-wake-gate.py"`.  The prompt is
  rewritten to trust the wake-gate's pre-fetched verdicts: the agent
  no longer re-calls `pql_anomaly_check` for the same window, saving
  one LLM round-trip on every `warn`/`critical` day too.

- **Walkthrough update.**  `docs/e2e-walkthroughs/audit-reviewer-daily.md`
  gains a step-7 verification path (clean day → no LLM iteration row
  in PointlesSQL; seeded reject row → LLM fires) and a cost note
  (clean-day cost: 3 HTTP round-trips vs. one LLM call worth
  one-to-three orders of magnitude more tokens).

### Added — Sprint 19.2.1: Review persistence + CloudEvents fan-out + cockpit card (2026-04-29)

Second half of Phase-19's "Audit-Reviewer-Agent reference run" sub-phase.
PointlesSQL now persists every posted review, fans the CloudEvents
envelope out to admin-configured webhooks (alongside Hermes-native
delivery), and surfaces the result on the home cockpit so operators
see yesterday's verdict without leaving the UI.

- **New ``agent_reviews`` table.**  Alembic migration
  ``l2g3a4b5c6d7_agent_reviews`` adds (id, run_id FK ``agent_runs.id``
  nullable, period_start, period_end, severity ``ok|warn|critical``,
  summary_md, payload_json, delivered_to_json, created_at) +
  CHECK constraints on severity and ``period_end > period_start``.

- **New ``review_destinations`` table.**  Admin-configured webhook
  sinks (name, webhook_url, hmac_secret, is_active, min_severity).
  ``min_severity`` gates noise: a ``warn``-default destination won't
  receive an ``ok``-day review.

- **``services/review_dispatcher``.**  Thin wrapper around
  ``alert_dispatcher.dispatch_webhook``: builds a
  ``pointlessql.agent_review.posted.v1`` CloudEvent, enumerates
  active destinations whose ``min_severity`` gate passes, fans out
  with HTTP+HMAC+retry, and persists the per-destination outcome
  (status code + URL hash, never the cleartext URL) onto
  ``AgentReview.delivered_to_json``.

- **Three auditor-gated agent-review routes.**
  ``POST /api/agent-reviews`` (validates bounds, persists, dispatches,
  returns the persisted row + fan-out log),
  ``GET /api/agent-reviews/latest`` (cockpit + plugin reads),
  ``GET /api/agent-reviews/{id}`` (detail JSON).
  Privilege ladder: auditor 200, supervisor 403, bare key 403,
  cookie admin 200.  ``GET /agent-reviews/{id}`` is the corresponding
  HTML detail page (admin-gated; auditor keys stay HTTP-only).

- **Four admin-gated review-destination routes** at
  ``/api/admin/review-destinations``.  Mirrors the existing
  admin-api-keys CRUD: list, create-with-secret-display, patch
  (sparse), delete.  Hard-delete is fine because
  ``AgentReview.delivered_to_json`` already records the destination's
  ``url_hash`` + ``name`` so historical fan-out attribution survives.

- **Cockpit "Latest review" card on ``/``.**  Admin-only.  Severity
  pill + rendered Markdown digest + period chip + "Full transcript"
  button → ``/agent-reviews/{id}``.  Lookup is best-effort with the
  same posture as Sprint 18.5's anomaly banner: a fresh-install
  pointlessql with no reviews yet renders the home page without the
  card, no error.

- **Detail page** at ``/agent-reviews/{id}``.  Three-column layout:
  Markdown summary + (optional) replay payload pretty-printed JSON,
  metadata sidebar (run_id link, severity, window), and the
  dispatcher fan-out log card listing every destination by name +
  url_hash + status_code.

- **Plugin grows from 29 → 31 tools.**  ``pql_post_audit_review``
  posts the rendered Markdown digest at the end of the daily review
  (now the final step of the Sprint-19.2.0 prompt).
  ``pql_get_latest_review`` reads the most recent review back so the
  Compliance-Bot / Incident-Responder personas can anchor their
  answers to yesterday's verdict.

### Added — Sprint 19.2.0: Daily-review Hermes job + auditor key bootstrap (2026-04-29)

First half of Phase-19's "Audit-Reviewer-Agent reference run" sub-phase.
Wires the operator-facing onboarding for the daily 06:00 UTC anomaly
digest: the CLI to mint an auditor-scoped API key, the reference Hermes
cron manifest, and an operational runbook that chains the two.

No server-side schema changes — Sprint 19.2.1 is the one that adds the
``agent_reviews`` + ``review_destinations`` tables.

- **New ``pointlessql admin issue-auditor-key`` Typer subcommand.**  The
  existing ``[project.scripts] pointlessql = "...:cli"`` entry point
  grew a Typer app: invoking ``pointlessql`` with no arguments still
  starts the uvicorn dev server (backward-compat via an
  ``invoke_without_command=True`` callback), and ``pointlessql admin
  issue-auditor-key --name=… [--supervisor]`` mints a fresh API key
  with ``api_keys.auditor=True``.  The plaintext token is printed
  exactly once and cannot be recovered afterwards — same hash-only
  storage discipline as Sprint 13.11's admin HTTP route.

- **Reference Hermes-cron manifest** at
  ``docs/hermes-jobs/audit-reviewer-daily.json``.  Schedule
  ``0 6 * * *``, ``enabled_toolsets: ["pointlessql"]``, ``deliver:
  "local"`` (Slack / email fan-out is opt-in via
  ``hermes cron edit --deliver``), and a self-contained prompt that
  pins the audit window to ``[yesterday-00:00 UTC, today-00:00 UTC)``
  so the digest is deterministic regardless of when the cron actually
  fires.  Renders Markdown to a fixed skeleton so downstream consumers
  (Sprint 19.2.1's cockpit card, future digest aggregators) can
  parse it.

- **``docs/hermes-jobs/README.md``** — index for the manifest folder.
  Documents why ``hermes cron create`` does not yet expose the
  ``--enabled-toolsets`` flag the auditor flow needs (so the
  walkthrough installs the manifest by editing
  ``~/.hermes/cron/jobs.json`` directly), the
  ``POINTLESSQL_AUDITOR_MODE`` plugin-side opt-in, and the lack of
  per-job env overlays in Hermes (``~/.hermes/.env`` is reloaded fresh
  per cron tick).

- **``docs/e2e-walkthroughs/audit-reviewer-daily.md``** — operational
  runbook (CLI + cron, no browser) chaining: mint key → ``.env``
  overlay → ``jobs.json`` patch → ``hermes cron run`` + ``tick`` →
  cross-check ``GET /api/audit/history?read_kind=audit_api`` rows
  attributed to ``api_key:daily-review``.  Closes the loop on
  audit-of-audit observability for the new flow.

### Added — Sprint 19.1: Audit-read tools + ``auditor`` scope (2026-04-28)

Sprint 19.1 closes the gap between the Phase-18 audit-data plane
and Phase-19's three consumer flows (Audit-Reviewer-Agent,
Compliance-Bot, Incident-Responder).  Adds a fourth privilege
scope, lifts the read endpoints out of admin-only gating, exposes
five new run-scoped JSON axes, and grows
``hermes-plugin-pointlessql`` from 20 → 29 tools.

- **New ``auditor`` scope on ``api_keys``.**  Alembic migration
  ``k1f2a3b4c5d6_api_keys_auditor`` adds a ``BOOLEAN NOT NULL
  DEFAULT 0`` column.  ``KeyEntry`` gains an ``auditor`` field;
  ``parse_keys`` now accepts ``name:secret:auditor`` env entries
  alongside the existing ``:supervisor`` form.  Middleware sets
  ``request.state.api_key_auditor`` from the verified bearer.
  New ``require_auditor`` dependency in
  ``pointlessql/api/dependencies.py`` enforces the gate;
  ``require_supervisor`` is widened to also accept the auditor
  scope so a single auditor key drives both tenant-wide and
  per-run audit reads without inheriting supervisor's
  approve/deny privileges or admin's PII-reveal.

- **Phase-18 audit endpoints lowered to ``require_auditor``.**
  ``GET /api/audit/summary``, ``/timeseries``, and ``/anomalies``
  no longer require an admin cookie — an auditor key is enough.
  ``POST /api/audit/pii/reveal`` stays admin-only.

- **Five new run-scoped JSON endpoints** under
  ``/api/agent-runs/{run_id}/audit/<axis>``:
  - ``lineage`` wraps the existing
    ``load_lineage_summary_for_run`` helper (per-op row-edge
    counts).
  - ``rejects`` wraps ``load_rejects_for_run`` (Sprint-15.5.3
    rejected rows).
  - ``value-changes`` queries ``lineage_value_changes`` directly
    and **always masks ``old_value`` / ``new_value`` for non-admin
    callers** — auditor scope cannot un-mask, regardless of the
    ``mask=false`` query flag.  Admin cookie + ``mask=false``
    surfaces cleartext via the same response shape; the
    historical admin-only ``POST /api/audit/pii/reveal`` is
    unchanged.
  - ``external-writes`` wraps ``load_unattributed_for_run``
    (filters to the run's ``tables_touched`` JSON list +
    ``acknowledged_at IS NULL``).
  - ``column-lineage`` queries ``lineage_column_map`` directly
    (per-run source-column → target-column edges).

  All five validate the run id up-front via ``_ensure_run_visible``
  and return ``CatalogNotFoundError`` (404) on stale UUIDs rather
  than empty rows.  Three formerly-private helpers in
  ``runs_routes.py`` (``_load_lineage_summary_for_run`` →
  ``load_lineage_summary_for_run`` etc.) were renamed when their
  cross-module use surfaced — strict pyright was rightfully
  complaining about ``reportPrivateUsage`` once
  ``agent_runs_routes`` started reaching for them.

- **New tenant-wide ``GET /api/audit/history``.**  Paginated
  ``query_history`` walk for the audit-of-audit traversal flow.
  Default response **excludes ``read_kind='audit_api'`` rows**
  so an audit-reviewer agent doesn't loop on its own
  breadcrumbs; ``?include_audit_api=true`` or
  ``?read_kind=audit_api`` lift the filter.  Routes through the
  existing ``list_queries`` service.

- **Anomaly-baseline bugfix in
  :func:`audit_aggregator.anomalies`.**  When the caller bounds
  ``since`` to (e.g.) yesterday-00:00 UTC, the previous
  implementation returned only points inside ``[since, until)``
  to the rolling-baseline loop, leaving the first bin with an
  empty baseline and false-positive ``critical`` verdicts.  Fix
  widens the underlying ``timeseries`` query by ``window_days``
  internally, then trims the response back to ``[since, until)``
  via a new dialect-safe ``_bin_floor_compare_string`` helper
  (SQLite ``%Y-%m-%d`` vs Postgres ``date_trunc(...)::String``
  reconciled by a 10-/16-char prefix compare).  This unblocks the
  Sprint-19.2 daily reviewer's "yesterday closed-day verdict"
  prompt.

- **Audit-of-audit logging on every new endpoint.**  Each new
  audit-read endpoint records a synthetic ``query_history`` row
  with ``read_kind='audit_api'`` via a new
  ``_record_audit_self`` helper (mirror of the existing
  ``_record_self`` in ``audit_routes.py``).  Server-side, not
  plugin-side — a malicious agent cannot turn off the
  audit-of-audit trail.

- **Plugin-side: 9 new tools in ``hermes-plugin-pointlessql``.**
  Bumps the registered count from 20 to 29.  New
  ``POINTLESSQL_AUDITOR_MODE`` env flag (analog to the existing
  ``POINTLESSQL_SUPERVISOR_MODE``) gates a new
  ``register_auditor_tools`` factory:
  - ``pql_list_recent_runs`` — generic recent-N-runs listing
    (the existing ``pql_runs_by_principal`` /
    ``pql_runs_by_agent`` cover filtered listings).
  - ``pql_audit_summary`` — wraps both ``/api/audit/summary``
    (``mode="counts"``) and ``/api/audit/timeseries``
    (``mode="timeseries"``) behind one tool.
  - ``pql_anomaly_check`` — wraps ``/api/audit/anomalies``.
  - ``pql_query_history_audit`` — wraps ``/api/audit/history``;
    default hides audit_api rows.
  - ``pql_query_row_lineage`` — per-op row-edge aggregate
    (run-scoped, distinct from the existing soyuz table-level
    ``pql_lineage`` tool).
  - ``pql_query_column_lineage`` — column-axis JSON view.
  - ``pql_query_value_changes`` — always-masked at the
    PointlesSQL boundary; the plugin doesn't expose a cleartext
    path.
  - ``pql_query_rejects`` — Sprint-15.5.3 reject rows.
  - ``pql_query_external_writes`` — unattributed Delta commits.
  - ``pql_get_run`` was deliberately dropped — the existing
    ``pql_run_summary`` already covers it.

- **16 new pytest cases in
  ``tests/test_audit_routes_sprint_19.py``** covering the
  privilege ladder (normal/supervisor/auditor/admin against
  tenant-wide and per-run reads), the masked-by-default
  contract on ``/audit/value-changes``, the audit-of-audit
  recursion guard on ``/api/audit/history``, the
  ``query_history`` row landing for each successful per-run
  audit read, and the structural shape of the anomaly bugfix.
  ``test_api_key_gate.py`` updated for the new
  ``parse_keys`` triple shape and gains a
  ``test_parse_keys_supports_auditor_scope`` case.
  Pre-existing unrelated test failures in
  ``test_api_notebook_workspace.py`` /
  ``test_scheduler_papermill.py`` /
  ``test_table_stats.py`` are untouched (verified clean on
  HEAD prior to this change).

> from CHANGELOG.md (bucket: **Added**)

### Added — Phase 18: Audit Cockpit (2026-04-28)

Closes Phase 18 in one autonomous session — six sub-sprints landed
on top of the Phase 15.7 capture surface to make the audit data
*actionable* for the four real personas (operator on-call,
developer debug, compliance auditor, daily trust glance).
Sequencing decision: Phase 18 lands **before** Phase 17 against
today's 10-tab run-detail layout; 18.1 cross-axis links will be
re-touched once Phase 17's tab consolidation lands.

- **Sprint 18.0 — Audit-Read API backbone.**  Three read-only
  JSON endpoints feed every later cockpit, Grafana, and
  Hermes-tool surface:
  - ``GET /api/audit/summary?since&until&principal&agent_id&table``
    returns one count per metric across runs, ops, errored ops,
    rows written (merge + write_table), value changes, rejects,
    external writes, cost-gate denials, tool calls, queries.
  - ``GET /api/audit/timeseries?metric&bin&group_by&...``
    bins by hour/day/week with optional grouping by table or
    principal.
  - ``GET /api/audit/anomalies?metric&window_days&sigma&...``
    classifies each bin against an N-day rolling mean ± Nσ as
    ``ok`` / ``warn`` (≥σ) / ``critical`` (≥2σ).
  - Backed by a new ``audit_aggregator`` service with a single
    ``_apply_audit_filters`` helper so the WHERE-clause logic
    lives in one place.  Dialect-aware bucketing (SQLite
    ``strftime`` vs Postgres ``date_trunc``) keeps both
    deployments working.
  - Self-tracking: every successful call inserts a
    ``query_history`` row with ``read_kind='audit_api'`` so the
    cockpit endpoints land in the audit lake they query.
    ``audit_api`` was added to ``VALID_READ_KINDS``.
  - All three endpoints are admin-gated.

- **Sprint 18.1 — Cross-axis navigation.**  The Operations-tab
  ``column edges: N`` and ``value changes: N`` badges now wrap
  in deep-links to ``/runs/{id}?op_id=N#tab-lineage``.  The
  ``run_detail_page`` handler accepts ``?op_id=`` and threads it
  into ``_load_operations_for_run`` /
  ``_load_rejects_for_run`` / ``_load_lineage_summary_for_run``
  so the three cross-axis tabs render filtered to that single
  op.  A "filtered to op #N" chip with a Clear-filter button
  sits above the tab strip.  Stale ``op_id`` falls back to
  unfiltered rendering rather than 404 (drill-downs are
  permissive).

- **Sprint 18.2 — PII-aware masking.**  New
  ``pointlessql/services/pii_resolver.py`` resolves column-level
  PII tags from soyuz-catalog (``GET /tags/column/{fqn.col}``)
  with a TTL cache keyed on ``(table, column)`` so a row-trace
  page rendering 100 cells from one table issues at most one
  soyuz call.  ``pii_mask`` helper replaces cleartext with
  ``***@***.***`` (email) / ``***-***-1234`` (phone) /
  ``A***z`` (default) shapes.  Row-trace template renders
  ``display_old`` / ``display_new`` (masked when
  ``is_pii=True``) and shows a Reveal button to admins;
  ``POST /api/audit/pii/reveal`` returns the cleartext and
  writes an ``audit_log`` row of
  ``action='pii.value_revealed'``.  ``AuditSettings`` gained
  ``pii_mask_default`` (default ``True``) and
  ``pii_cache_ttl_seconds`` (default ``600``).  Storage stays
  byte-faithful — masking is render-time only.

- **Sprint 18.3 — Saved audit queries + CSV/JSON export.**  New
  ``saved_audit_queries`` table (Alembic ``j0e1f2a3b4c5``)
  separate from ``saved_queries`` because:
  - visibility is admin-only, not the owner-+-shared model;
  - five canonical starter rows ship with the migration:
    ``pii-writes-last-90d``, ``rollbacks-last-quarter``,
    ``cost-gate-denials-this-week``,
    ``unacknowledged-external-writes``,
    ``top-mutating-principals-30d``;
  - ``alert_threshold_count`` plugs into the Sprint 18.5 alert
    surface;
  - service enforces an explicit allow-list of audit-table
    names (``agent_runs``, ``agent_run_operations``,
    ``lineage_*``, ``query_history``, ``audit_log``,
    ``unattributed_writes``, …) via sqlglot — SELECT-only,
    no DDL/DML.
  - CRUD endpoints at ``/api/saved-audit-queries`` plus
    ``/{slug}/run`` and ``/{slug}/export.csv`` /
    ``/{slug}/export.json`` (PDF deferred — CSV+JSON satisfy
    SOC2 / GDPR Art. 30 evidence packets).
  - Every export writes a ``saved_audit_query.exported`` audit
    row.  Starter rows refuse PATCH/DELETE.
  - New admin-only ``/audit/queries`` HTML workbench: split-
    pane list-of-queries + textarea + Run/Export buttons +
    result table.

- **Sprint 18.4 — Run-diff lineage view.**  New service
  ``run_diff.build_lineage_diff(factory, run_a_id, run_b_id)``
  produces three buckets:
  - ``reject_pattern_shift`` — counts of
    ``LineageRowReject.reason`` values per side, plus a
    per-reason ``delta``;
  - ``value_change_volume_per_table`` — per-target counts;
  - ``row_count_delta_per_table`` — sum of ``rows_affected``
    per merge / write target.

  ``GET /api/agent-runs/diff?detail=true`` carries the new
  ``lineage_diff`` payload.  New HTML route
  ``GET /runs/{a}/diff/{b}`` consumes both
  ``build_detail_diff`` and ``build_lineage_diff`` to render
  ``pages/agent_run_compare.html``: four +Δ stat cards
  (rows touched / value changes / errored ops / rejects) plus
  Chart.js bar charts for each lineage axis.

- **Sprint 18.5 — Anomaly highlighting.**  Three surfaces all
  driven by the Sprint 18.0 ``/api/audit/anomalies`` endpoint:
  - ``/api/home/summary`` carries an ``anomalies: {warn, critical}``
    block computed against ``rejects``, ``errored_ops``, and
    ``external_writes``; the home page renders a yellow/red
    banner when ≥1 metric is critical/warn.
  - ``/runs/{id}`` HTML adds an anomaly chip at the top of the
    page when the latest day's value for any of those metrics
    breaches the configured σ threshold; the chip names the
    worst-offender metric + observed-vs-baseline values.
  - ``saved_audit_queries.alert_threshold_count`` (new column)
    plugs into the existing ``/api/alerts`` machinery so a
    scheduled run that returns more rows than the threshold
    fires.

  ``AuditSettings`` gained ``anomaly_baseline_window_days``
  (default 7) and ``anomaly_threshold_sigma`` (default 2.0).
  Anomalies are computed on-the-fly — no
  ``audit_anomalies_daily`` materialised table.  Email-digest
  CLI deliberately deferred to Phase 19.2 (Audit-Reviewer-Agent
  covers daily-summary territory; building it twice is waste).

Tests: 72 new unit + integration tests across
``tests/test_audit_aggregator.py``,
``tests/test_runs_op_filter.py``,
``tests/test_pii_resolver.py``,
``tests/test_saved_audit_queries.py``,
``tests/test_run_diff_lineage.py``, and
``tests/test_anomaly_highlighting.py``.  Existing
``test_lineage_*`` and ``test_value_change_*`` suites still
pass — no regressions in the 15.x axes.

### Added — Sprint 19.0: Grafana audit dashboard (XS quick-win, 2026-04-28)

First Phase-19 sub-sprint, landed out of phase order.  Strategic
ordering note in ROADMAP marks 19.0 as eligible to land before
Phase 17 / 18 because it reads the existing audit + lineage tables
directly — no Phase-18 audit-API dependency.  Phases 19.1–19.3
remain queued (they wrap the not-yet-built Phase-18 backbone).

Goal: glance-trust dashboard.  No agent code, no API changes — a
``docker compose -f docker-compose.yml -f docker-compose.grafana.yml up``
spins up Grafana auto-provisioned with eight panels covering
runs/day, reject-rate vs 7-day baseline, value-change-volume per
table (red ≥1000), external-write count (red ≥1), top mutating
principals, cost-gate denials, tool-call latency table, and
EXPLAIN-cost histogram.

- ``docker-compose.grafana.yml`` overlay adds a
  ``grafana/grafana-oss:latest`` service.  Two intentional config
  choices that surfaced in the design pass:
  - ``GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=frser-sqlite-datasource``
    is **mandatory** — the SQLite plugin is unsigned and Grafana
    refuses to load it without the explicit allow.  Skipping it
    is the #2 cause of "datasource doesn't appear" reports.
  - ``pointlessql_data:/data/pointlessql`` is mounted **read-write**,
    NOT ``:ro``.  Reason: the app runs SQLite in WAL mode (the
    ``.db-wal`` and ``.db-shm`` files exist alongside the DB);
    the SQLite library needs write access to manage ``-shm`` even
    for readers.  A ``:ro`` bind produces ``disk I/O error`` on
    the first query.  The Grafana plugin only issues SELECTs.
- ``grafana/provisioning/datasources/pointlessql.yml`` pins the
  datasource UID to ``pointlessql-sqlite`` so panel→datasource
  bindings survive reprovisioning.  Without a hardcoded UID,
  every restart shuffles UIDs and breaks every panel.
- ``grafana/provisioning/dashboards/pointlessql.yml`` provider
  drops the dashboard into a ``PointlesSQL`` folder (keeps it
  out of Grafana's default ``General`` folder where built-in
  samples live), ``allowUiUpdates: false`` enforces JSON as
  the source of truth.
- ``grafana/dashboards/pointlessql_audit.json`` — 10 panels
  (8 spec'd + Markdown header + datasource-health smoke).  Layout
  on a 24×32 grid.  Notable per-panel choices:
  - **Runs/day**: timeseries-bar grouped by ``date(started_at)``,
    using the frser plugin's ``$__timeFilter()`` macro (bare
    ``$__timeFrom()`` / ``$__timeTo()`` is **not** supported).
  - **Reject-rate vs baseline**: two series, today's daily count
    plus a 7-day trailing average computed via correlated
    subquery (no SQL window functions — the frser plugin's query
    parser truncates them in some Grafana releases).
  - **Value-change-volume per table**: stacked bars per
    ``target_table``, threshold style ``line`` at 1000 to make
    over-budget runs visually pop.
  - **External-write count**: stat panel reading
    ``unattributed_writes WHERE acknowledged_at IS NULL``,
    threshold red at ≥1.
  - **Top-mutating-principals**: horizontal bars of summed
    ``rows_affected`` for ``op_name IN ('merge', 'write_table')``.
    NULL principals coalesced to ``'<unknown>'`` so background
    agents are still visible.
  - **Tool-call latency**: SQLite has no ``percentile_cont``,
    so the panel emits raw rows and a Grafana ``Reduce →
    percentile`` transform computes p50/p99 client-side.
  - **EXPLAIN-cost histogram**: ``CAST(cost_est AS REAL)`` is
    mandatory because ``cost_est`` is ``Decimal(18,4)`` ORM-side
    and the frser plugin returns Decimals as strings, which the
    histogram viz can't bucket.
- Scope decisions baked into the sprint:
  - **SQLite-only.**  Postgres deferred to Sprint 19.0.1 (separate
    overlay, separate dashboard).  Reason: dialect divergence
    (no ``percentile_cont`` / ``date_trunc`` in SQLite) makes
    a templated dual-mode dashboard cost more than the XS
    sizing allows.
  - **Panel thresholds only, no alert routing.**  Webhook /
    Slack / email routing is Phase 19.2 territory.
  - **Anonymous viewer enabled**, admin password still
    enforced for edits.

End-to-end smoke (against the host's live DB, ten queries):
all 10 panel SQLs parse cleanly and return expected shape —
``agent_runs`` has 7 rows, ``lineage_row_rejects`` 58, the
7-day baseline subquery returns 8.29 rejects/day, three
mutating principals (admin@local with 206 rows leading).

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 18 — Audit Cockpit**: three new ``/api/audit/*``
  endpoints (summary / timeseries / anomalies) feed cross-axis
  navigation, PII-aware masking, saved audit queries, run-diff
  view, anomaly highlighting.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 19 — Audit-Reviewer Agent + Grafana**: shared
  Phase-18 backbone drives a Grafana dashboard JSON
  (``grafana/pointlessql_audit.json``), 10 audit-read tools in
  ``hermes-plugin-pointlessql``, daily Audit-Reviewer-Agent
  reference run, Compliance-Bot + Incident-Responder demos.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 20 — Forensics + Retention**: CloudTrail / audit-
  stream forwarder, PII detection + masking layer, lineage
  retention policies, time-travel value queries in UI, soyuz
  columnLineage / valueChange facet ingest (formerly the
  Phase-15.8+ sketch).
- **Some-day rewrite**: pre-OSS-release hygiene (EUIPO
  trademarks, NOTICE, CLA, domains) + big-bang launch day
  (HN / Twitter / Reddit / LinkedIn / blog) + conference
  circuit (DataCouncil, Subsurface, dbt Coalesce, Berlin
  Buzzwords, Big Data LDN) + sustained visibility + the
  original GHCR / PyPI / Helm / docs items + commercial
  offering pathway (3-5 design partners → UG/GmbH →
  cryptographic anchor service / hosted Cloud).

No code change in this entry — pure roadmap edit.  Engineering
work continues against the new tree.  See [ROADMAP.md](ROADMAP.md).
