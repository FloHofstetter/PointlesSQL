# Hermes job manifests for PointlesSQL

This folder holds reference Hermes-cron job manifests that drive
PointlesSQL's "agents reviewing agents" surface. The manifests are
plain JSON snippets shaped like a single entry of `~/.hermes/cron/jobs.json`
— see [`hermes-agent/cron/jobs.py:create_job`](../../../hermes-agent/cron/jobs.py)
for the field set the scheduler reads.

PointlesSQL never executes these manifests itself. Hermes is the runtime;
PointlesSQL is the audit data store + tool surface they call into.

## Available manifests

| File | Phase | Persona | Schedule | Purpose |
|---|---|---|---|---|
| [`audit-reviewer-daily.json`](audit-reviewer-daily.json) | 19.2 | Reviewer | `0 6 * * *` | Daily anomaly digest of yesterday's agent activity. Wake-gate (`scripts/audit-wake-gate.py`) skips the LLM round-trip on `ok` days; on `warn`/`critical` the agent drafts Markdown, persists it via `pql_post_audit_review`, and PointlesSQL fans the CloudEvent out to webhooks. |

(More personas land in 19.3 / 19.4 — Compliance-Bot and Incident-Responder.)

## Installing a manifest

The Hermes CLI command `hermes cron create` does not yet expose
`--enabled-toolsets`, which the auditor flow needs to scope tools.
Until that lands, install manifests by editing `~/.hermes/cron/jobs.json`
directly:

1. Make sure `~/.hermes/cron/` exists (`mkdir -p ~/.hermes/cron`).
2. If `~/.hermes/cron/jobs.json` does not yet exist, create it with
   `[]` as the file body.
3. Open the file, paste the manifest entry into the top-level array,
   give it a fresh 12-hex-char `id` (`uuid4().hex[:12]`), and save.
4. Restart the Hermes gateway (or run `hermes cron tick --once` in
   the foreground if you only want a one-off).

The walkthrough at [`docs/e2e-walkthroughs/audit-reviewer-daily.md`](../e2e-walkthroughs/audit-reviewer-daily.md)
spells the install out step by step, including the prerequisite
`pointlessql admin issue-auditor-key` step and the `~/.hermes/.env`
overlay.

## Authentication & the auditor scope

The audit-read tools the manifests call (`pql_audit_summary`,
`pql_anomaly_check`, `pql_list_recent_runs`,
`pql_query_history_audit`, `pql_query_row_lineage`,
`pql_query_column_lineage`, `pql_query_value_changes`,
`pql_query_rejects`, `pql_query_external_writes`) are gated behind
two things:

1. The plugin's `POINTLESSQL_AUDITOR_MODE` env var (which makes the
   plugin register the 9 auditor tools at session start).
2. A PointlesSQL API key with the `auditor` scope set on it
   (`api_keys.auditor=True`, added in Sprint 19.1's Alembic
   migration `k1f2a3b4c5d6`). Mint one with:
   ```bash
   pointlessql admin issue-auditor-key --name=daily-review
   ```
   The CLI prints the bearer token exactly once — copy it into
   `~/.hermes/.env` as `POINTLESSQL_API_KEY=<token>` immediately.

Both knobs are read at Hermes-cron run time from `~/.hermes/.env`
(Hermes reloads the dotenv on every cron run; see
`hermes-agent/cron/scheduler.py` around line 825). There is currently
no per-job env overlay in Hermes, so all cron jobs in the same
Hermes install share the same auditor key. If you need separate keys
per job, add a Hermes-side feature first.

## Prompt design notes

- The prompt always pins the time window the agent should review.
  Daily-review uses `[yesterday-00:00 UTC, today-00:00 UTC)`, which
  is closed-day so the response is deterministic regardless of when
  the cron actually fires.
- The prompt forbids any write-side tools by name. The auditor scope
  on the API key already blocks them server-side — the prompt rule
  is belt-and-braces and saves an LLM round-trip when the agent gets
  curious.
- The prompt never asks the agent to "be creative" with the output
  shape. The Markdown skeleton is fixed because downstream consumers
  (Sprint 19.2.1's cockpit card, future digest aggregators) parse
  the same shape.
- The wake-gate at [`scripts/audit-wake-gate.py`](../../scripts/audit-wake-gate.py)
  pre-fetches the anomaly verdicts and prints them as the leading
  `#`-prefixed context block. The agent trusts that block and does
  not re-call `pql_anomaly_check` — saves one LLM round-trip on
  `warn`/`critical` days and skips the LLM entirely on `ok` days
  (the script's last line is `{"wakeAgent": false}` then; see
  `cron/scheduler.py:_parse_wake_gate`).
- The final tool call is always `pql_post_audit_review`. PointlesSQL
  is the source of truth — the cockpit "Latest review" card and the
  webhook fan-out both read from `agent_reviews`. Hermes-native
  delivery (`deliver: "slack:…"`) is a parallel best-effort path on
  top, useful when PointlesSQL is briefly unreachable but the chat
  channel still needs the digest.
