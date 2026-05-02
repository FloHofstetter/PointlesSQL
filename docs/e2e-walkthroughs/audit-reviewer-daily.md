# Audit-Reviewer-Agent daily-review walkthrough

Exercises the reference Hermes cron: a daily 06:00 UTC
agent run that summarises yesterday's PointlesSQL audit activity and
delivers Markdown to a configured sink.

Unlike the Playwright-driven UI walkthroughs in the rest of this
folder, this one is an **operational runbook**. It chains:
- the new [`pointlessql admin issue-auditor-key`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py)
 CLI subcommand,
- the [`audit-reviewer-daily.json`](../integrations/hermes-jobs/audit-reviewer-daily.json)
 Hermes-cron manifest, and
- the [`hermes cron tick`](https://github.com/FloHofstetter/hermes-agent/blob/main/cron/scheduler.py)
 scheduler run.

Each step lists the exact command to run plus what to assert in the
output. There is no browser, no Alpine, no `mcp__playwright__*` calls.

## Preconditions

- Hermes is installed and `hermes` is on `$PATH`. `~/.hermes/.env`
 exists (even if empty).
- `hermes-plugin-pointlessql` is installed in the same Hermes
 virtualenv. Run `hermes plugins list` and confirm `pointlessql`
 appears.
- PointlesSQL is running locally on `http://127.0.0.1:8000`. The
 default config from
 [`docs/install.md`](../getting-started/installation.md) is fine.
- At least one historical agent_run exists in the PointlesSQL DB
 (any prior plugin run will have created one). Without seed data
 the walkthrough still works; the agent simply reports "nothing of
 note".

## Walkthrough

1. **Mint an auditor-scoped API key.**
 - Action: from the PointlesSQL checkout,
 ```bash
 uv run pointlessql admin issue-auditor-key --name=daily-review
 ```
 - Assert: stdout shows
 ```
 name = daily-review
 prefix = …
 auditor = True
 supervisor = False
 created_at = …
 ```
 followed by the bearer token. The token is shown exactly once.
 - Re-running the command with the same `--name` exits with
 `error: API key 'daily-review' already exists` (status 2).
 `pointlessql admin --help` lists `issue-auditor-key`.

2. **Drop the auditor settings into `~/.hermes/.env`.**
 - Action: append (creating the file if needed):
 ```
 POINTLESSQL_BASE_URL=http://127.0.0.1:8000
 POINTLESSQL_API_KEY=<token from step 1>
 POINTLESSQL_AUDITOR_MODE=1
 POINTLESSQL_PRINCIPAL=audit-reviewer-agent
 ```
 - Assert: `grep AUDITOR ~/.hermes/.env` shows the two new lines.
 No spaces around `=`. No quotes around the token (Hermes' dotenv
 loader strips them, but the manifest assumes the raw value).

3. **Install the manifest into the Hermes cron store.**
 - Action: ensure `~/.hermes/cron/jobs.json` is a JSON array, then
 paste a copy of [`audit-reviewer-daily.json`](../integrations/hermes-jobs/audit-reviewer-daily.json)
 into the array. Mint a fresh 12-hex-char `id` (e.g.
 `python3 -c 'import uuid; print(uuid.uuid4().hex[:12])'`) and
 set the `id` field on the entry. Strip the leading `_comment`
 key — Hermes does not error on extra keys, but stripping it
 keeps the file clean.
 ```bash
 mkdir -p ~/.hermes/cron
 test -f ~/.hermes/cron/jobs.json || echo '[]' > ~/.hermes/cron/jobs.json
 # …edit jobs.json with your editor of choice…
 ```
 - Assert: `hermes cron list` shows the new job:
 ```
 audit-reviewer-daily every day at 06:00 UTC next: <tomorrow 06:00>
 ```
 `last_status` is `null` until the first run.

4. **Force an immediate test run.**
 - Action: trigger the scheduler tick directly so we don't wait
 until 06:00:
 ```bash
 hermes cron run <job_id>
 hermes cron tick
 ```
 `hermes cron run` flips the job's `next_run_at` to "now"; the
 subsequent `tick` actually executes. (Some Hermes builds expose
 `hermes cron tick --once`; either works.)
 - Assert: a few seconds later, `hermes cron list` shows
 `last_status: ok` and `last_run_at` set to a fresh timestamp.
 A new file appears under `~/.hermes/cron/output/<job_id>/<ts>.md`
 containing the rendered Markdown. The first heading line matches
 `## Audit Review — YYYY-MM-DD`.

5. **Cross-check the audit-of-audit trail in PointlesSQL.**
 - Action: while still authenticated as the auditor key,
 ```bash
 curl -s -H "Authorization: Bearer <token>" \
 "http://127.0.0.1:8000/api/audit/history?include_audit_api=true&read_kind=audit_api&limit=20" | jq.
 ```
 - Assert: at least four `read_kind: "audit_api"` rows landed in
 the last few minutes — one per audit-tool call the agent made
 (`pql_audit_summary` plus three `pql_anomaly_check` invocations
 at minimum, more on `warn`/`critical` days). Each row's
 `user_email` reads `api_key:daily-review` (the `user_email`
 column carries `api_key:<name>` for bearer-authenticated calls —
 see 's `_audit_helpers`).
 - This proves the daily review is itself auditable: any attempt to
 hide activity in the digest can be cross-checked against the
 query_history rows the agent generated while drafting it.

6. **Delivery sink (optional).**
 - The reference manifest sets `deliver: "local"` — output stays
 in the cron-output file from step 4. To fan out to Slack /
 email / a webhook, edit the job:
 ```bash
 hermes cron edit <job_id> --deliver "slack:<channel-id>"
 ```
 Hermes' platform adapter handles auth (see
 [`hermes-jobs/README.md`](../integrations/hermes-jobs/README.md)).
 - Assert: re-run via `hermes cron run <job_id> && hermes cron tick`,
 confirm the Slack channel got a Markdown post matching
 `~/.hermes/cron/output/<job_id>/<ts>.md`.
 - also persists every review back into PointlesSQL
 (the agent's last tool call is `pql_post_audit_review`).
 `/api/agent-reviews/latest` returns the row; the home page
 renders a "Latest review" card. Configure additional outbound
 CloudEvents webhooks under `/admin/review-destinations`.

7. **Wake-gate verification.**
 - The reference manifest carries `script:
 "scripts/audit-wake-gate.py"`. On a yesterday-was-quiet day the
 script's last stdout line is `{"wakeAgent": false}` and Hermes
 skips the LLM round-trip entirely. On a `warn`/`critical` day
 the same script's stdout (the pre-fetched anomaly summary) gets
 prepended to the agent's prompt as context, so the LLM doesn't
 re-fetch the same data.
 - Smoke test: clear yesterday's reject + external-write history
 from PointlesSQL (or just run on a fresh DB) and trigger the
 job. `hermes cron list` shows `last_status: ok` but no
 `iteration` row landed in PointlesSQL — the agent never woke.
 Then seed a single rejected row "yesterday", re-run the job,
 and assert the LLM did fire (a fresh `agent_reviews` row +
 fresh tool-call rows in `query_history`).
 - Cost: on a clean day the wake-gate burns one HTTP round-trip per
 metric (3 total) instead of an LLM call worth roughly one to
 three orders of magnitude more tokens. Over a quarter of clean
 days that's the difference between zero and ~90 LLM rounds.

## Cleanup

Optional, only if you minted the key + manifest just for the
walkthrough:

```bash
hermes cron remove <job_id>
# in PointlesSQL:
curl -s -X DELETE -H "Authorization: Bearer <admin-token>" \
 http://127.0.0.1:8000/api/admin/api-keys/daily-review
# or, programmatically:
uv run python -c "from pointlessql.db import get_session_factory, init_db; \
 from pointlessql.settings import Settings; \
 from pointlessql.services import api_keys; \
 init_db(Settings().db.url); \
 print(api_keys.revoke_api_key(get_session_factory(), name='daily-review'))"
```

## Known limitations

- **No per-job env overlay in Hermes.** All cron jobs in the
 install share `~/.hermes/.env`. If you want job-specific keys,
 add Hermes-side feature support first; the manifest does not
 carry an `env` field.
- **`hermes cron create` does not expose `--enabled-toolsets`.**
 Step 3 has to edit `jobs.json` directly until the Hermes CLI
 catches up. Tracking issue lives in `hermes-agent`.
- **Hermes reloads `~/.hermes/.env` every cron tick.** Rotating
 the auditor key only requires editing the dotenv; no Hermes
 restart needed. (Confirmed at `cron/scheduler.py` ~line 825.)
