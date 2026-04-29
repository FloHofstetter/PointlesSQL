# Audit-stream sinks walkthrough (Sprint 20.0)

Exercises the Phase 20 audit-stream forwarder: governance
CloudEvents (external-write detection, cost-gate denials,
audit-export issuance, lineage prunes) fire to admin-configured
sinks of three types — webhook, S3, AWS CloudTrail.

Like the [audit-reviewer-daily](audit-reviewer-daily.md)
walkthrough this is an **operational runbook**, not a
browser-driven scenario. The audit-sinks admin UI is bare-bones
JSON-only in this sprint (no `frontend/templates/pages/` page yet);
admins drive the flow via `curl` or `httpie`.

## Preconditions

- PointlesSQL is running on `http://127.0.0.1:8000` with the
  Sprint-20.0 migration applied (`alembic upgrade head` →
  `m3h4i5j6k7l8`).
- An admin login cookie or admin API key is available
  (`pointlessql admin issue-auditor-key --name=test` won't work
  here — these routes need `require_admin`, i.e. an admin/system
  scope, not auditor).
- `POINTLESSQL_AUDIT_STREAM_ENABLED=1` is set in the running
  process's env. Without it the governance row still persists
  but every sink is skipped (`outcome=no_destination`).
- For the webhook step, a local listener you control. The
  walkthrough uses `httpbin.org/post` for simplicity but
  production deploys should pick a real sink (Slack incoming
  webhook, Splunk HEC, etc.).

## Walkthrough

1. **Register a webhook sink.**

   ```bash
   curl -sS -X POST http://127.0.0.1:8000/api/admin/audit-sinks \
     -H 'Content-Type: application/json' \
     -b cookies.txt -c cookies.txt \
     -d '{
       "name": "test-webhook",
       "type": "webhook",
       "config": {"url": "https://httpbin.org/post"}
     }' | jq
   ```

   Assert: response includes `"id": 1`, `"type": "webhook"`,
   `"is_active": true`, and `"config"` does **not** echo any
   secret.

2. **Send a synthetic test envelope.**

   ```bash
   curl -sS -X POST \
     http://127.0.0.1:8000/api/admin/audit-sinks/1/test \
     -b cookies.txt | jq
   ```

   Assert: `"ok": true`. Httpbin echoes the canonical envelope —
   open the httpbin URL it returned to verify the body shape.

3. **Trigger a real governance event (audit-export).**

   ```bash
   curl -sS -b cookies.txt \
     'http://127.0.0.1:8000/admin/audit/export?fmt=json&since=24h' \
     -o /tmp/audit.json
   ```

   Assert: `/tmp/audit.json` downloads. Then list recent events:

   ```bash
   curl -sS -b cookies.txt \
     http://127.0.0.1:8000/api/admin/audit-sinks/recent-events | jq '.events[0]'
   ```

   The first row should be
   `pointlessql.audit_export.issued`, `outcome="delivered"`, fired
   moments ago.

4. **Trigger an external-write detection (synthetic).**

   In a Python shell:

   ```python
   from pathlib import Path
   import deltalake, pandas as pd
   df = pd.DataFrame({"x": [1, 2, 3]})
   deltalake.write_deltalake(Path("/tmp/external_table"), df, mode="overwrite")
   ```

   Then trigger a scan:

   ```bash
   curl -sS -X POST \
     http://127.0.0.1:8000/api/admin/external-writes/scan \
     -b cookies.txt | jq
   ```

   Assert: `recent-events` now shows
   `pointlessql.external_write.detected` for the synthetic table.

5. **Trigger a cost-gate denial.**

   ```bash
   curl -sS \
     'http://127.0.0.1:8000/api/sql/explain?sql=SELECT%20*%20FROM%20generate_series(1,2000000000)' \
     -b cookies.txt | jq
   ```

   Assert: `needs_approval=true`. `recent-events` now contains
   `pointlessql.cost_gate.denied`.

6. **Add an S3 sink (optional, requires AWS creds).**

   ```bash
   curl -sS -X POST http://127.0.0.1:8000/api/admin/audit-sinks \
     -H 'Content-Type: application/json' \
     -b cookies.txt \
     -d '{
       "name": "s3-archive",
       "type": "s3",
       "config": {
         "bucket": "my-audit-archive",
         "prefix": "pointlessql/governance",
         "region": "eu-central-1",
         "access_key_id": "AKIA…",
         "secret_access_key": "…"
       }
     }' | jq
   ```

   Trigger a test envelope (`POST /api/admin/audit-sinks/{id}/test`)
   and confirm the object lands at
   `s3://my-audit-archive/pointlessql/governance/pointlessql.audit_sink.test/<yyyy>/<mm>/<dd>/<event_id>.json`.

7. **Add an AWS CloudTrail sink (optional, requires CloudTrail
   Lake channel).**

   ```bash
   curl -sS -X POST http://127.0.0.1:8000/api/admin/audit-sinks \
     -H 'Content-Type: application/json' \
     -b cookies.txt \
     -d '{
       "name": "cloudtrail-prod",
       "type": "aws_cloudtrail",
       "config": {
         "region": "us-east-1",
         "channel_arn": "arn:aws:cloudtrail:us-east-1:111122223333:channel/abcd",
         "event_source": "pointlessql.audit",
         "access_key_id": "AKIA…",
         "secret_access_key": "…"
       }
     }' | jq
   ```

   Trigger a test envelope and verify the event appears in the
   CloudTrail Lake event-data store linked to the channel.

## Cleanup

```bash
# delete sinks created above
curl -sS -X DELETE -b cookies.txt http://127.0.0.1:8000/api/admin/audit-sinks/1
```

The synthetic Delta table at `/tmp/external_table` and the
downloaded `/tmp/audit.json` are local artifacts; remove at will.

## Bug-hunt notes

There is no UI page for audit-sink management in this sprint —
admins drive everything via JSON. A `frontend/templates/pages/admin_audit_sinks.html`
page is queued for Phase 20.5 (close memo + bug-hunt sweep) once
the underlying API has settled.
