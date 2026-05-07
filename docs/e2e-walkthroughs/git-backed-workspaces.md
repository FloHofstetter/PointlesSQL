# Git-Backed Workspaces — register, sync, render

> **Mode:** `curl` · **Phase:** 51 · **Surface:** Admin JSON API + webhook

Replays the Phase-51 happy path: a data team commits
`pointlessql.yaml` to their repo; an admin registers the URL
through the JSON API; a sync materialises the data product +
dashboards + saved queries into PointlesSQL; subsequent commits
flow in via webhook or cron.

## Setup

1. Start PointlesSQL with the workspace-repos defaults — no env
   vars required for the basic flow:

   ```bash
   uv run pointlessql
   ```

2. Build a local bare repo as the upstream (the walkthrough
   keeps everything on the local filesystem so no GitHub
   account is required):

   ```bash
   mkdir -p /tmp/walkthrough-seed && cd $_
   git init --initial-branch=main
   git config user.email walkthrough@example.com
   git config user.name "Walkthrough"
   cat > pointlessql.yaml <<'YAML'
   data_product:
     name: Sales Orders
     version: "1.0.0"
     catalog: main
     schema: sales_gold
     steward_email: alice@example.com
     sla_minutes: 60
     tables:
       - name: orders
         primary_key: [order_id]
         columns:
           - {name: order_id,    type: long,      nullable: false}
           - {name: order_total, type: double,    nullable: true}
           - {name: ordered_at,  type: timestamp, nullable: false}

   dashboards:
     - slug: weekly-orders
       title: Weekly orders volume
       notebook_path: dashboards/weekly_orders.py
   YAML
   git add pointlessql.yaml
   git commit -m "initial yaml"
   git clone --bare /tmp/walkthrough-seed /tmp/walkthrough-bare.git
   ```

## Register the repo

```bash
curl -X POST http://localhost:8000/api/admin/repos \
     -H "Cookie: <admin-session>" \
     -H "Content-Type: application/json" \
     -d '{
       "slug": "platform-yaml",
       "url": "file:///tmp/walkthrough-bare.git",
       "default_branch": "main",
       "provider_kind": "generic"
     }'
```

Response carries the freshly-generated `webhook_secret` exactly
once; persist it now or rotate via
`POST /api/admin/repos/{id}/rotate-webhook-secret` later.
Subsequent `GET /api/admin/repos/{id}` calls never echo the
plaintext.

## Sync manually

```bash
curl -X POST http://localhost:8000/api/admin/repos/<id>/sync \
     -H "Cookie: <admin-session>"
```

Expected: `ok=true`, `operation="clone"`,
`loaded_data_products=1`, `loaded_conventions=1`.  The data
product surfaces under `/data-products` immediately.

A second call reports `operation="pull"` and
`changed=false` against the unchanged upstream.

## Modify the upstream + sync again

```bash
cd /tmp/walkthrough-seed
sed -i 's/version: "1.0.0"/version: "1.1.0"/' pointlessql.yaml
git commit -am "bump version"
git push file:///tmp/walkthrough-bare.git main
```

Trigger another sync; the `/data-products/main/sales_gold`
detail page now shows the new version.

## Webhook-triggered sync (optional)

```bash
SIG=$(python3 -c "
import hashlib, hmac, json, sys
secret = sys.argv[1]
body = sys.argv[2].encode()
print('sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest())
" "$WEBHOOK_SECRET" '{"ref":"refs/heads/main","after":"deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}')

curl -X POST http://localhost:8000/webhook/git/<id> \
     -H "X-GitHub-Event: push" \
     -H "X-Hub-Signature-256: $SIG" \
     -H "Content-Type: application/json" \
     -d '{"ref":"refs/heads/main","after":"deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}'
```

Response is 202 with `status="scheduled"`; the actual sync
runs in the background.

## Cron-triggered sync (optional)

Set `POINTLESSQL_REPOS_SYNC_INTERVAL_SECONDS=60` in the
process env and restart.  The lifespan loop pulls every stale
repo every 60 seconds.

## Agent flow (Hermes plugin)

```python
from hermes_plugin_pointlessql import PointlessClient

client = PointlessClient(...)
print(client.list_workspace_repos())
print(client.get_workspace_repo(slug="platform-yaml"))
print(client.trigger_workspace_repo_sync(slug="platform-yaml"))
print(client.workspace_repo_sync_history(slug="platform-yaml"))
```

The four matching tools are exposed through Hermes:
`pql_list_workspace_repos`, `pql_get_workspace_repo`,
`pql_trigger_repo_sync`, `pql_repo_sync_history`.

## Anti-goals

- The yaml is canonical; the admin UI does **not** edit it.
  Git-blame is the audit log.
- Repo-backed notebooks resolve via
  `repo:<workspace_id>:<slug>/<rel>.py` and are read-only.
- Repo-loaded dashboards / saved queries carry
  `source="repo:<slug>"` and are overwritten by the next sync.
