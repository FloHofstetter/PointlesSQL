---
title: Authorization coverage matrix (generated)
audience: contributor
---

# Authorization coverage matrix

**Generated** by `scripts/authz_matrix_generate.py` — do not hand-edit; regenerate after adding routes.

Status is one of **role-gated** (explicit `require_*` dependency), **public** (on the unauthenticated `PUBLIC_PREFIXES` allowlist), or **authenticated** (the global auth middleware requires a logged-in principal — the safe default, not a gap).

Total routes: 817 · role-gated: 42 · public: 20 · authenticated: 755

## ⚠️ Admin-path routes without a role gate

These paths look privileged (contain `/admin`) but carry no `require_*` role gate — a reviewer should confirm each is meant to be reachable by any authenticated user, or add `require_admin`.

| Method | Path |
| --- | --- |
| GET | `/admin` |
| GET | `/admin/api-keys` |
| GET | `/admin/api-keys/{name}` |
| GET | `/admin/audit` |
| GET | `/admin/audit-sinks` |
| GET | `/admin/audit/export` |
| GET | `/admin/audit/export.tar.gz` |
| GET | `/admin/audit/saved-filters` |
| POST | `/admin/audit/saved-filters` |
| DELETE | `/admin/audit/saved-filters/{filter_id}` |
| PUT | `/admin/audit/saved-filters/{filter_id}` |
| GET | `/admin/cdf-subscriptions` |
| GET | `/admin/data-product-apply` |
| GET | `/admin/domains` |
| GET | `/admin/entity-discovery` |
| GET | `/admin/external-writes` |
| GET | `/admin/glossary` |
| GET | `/admin/governance` |
| GET | `/admin/mesh-dashboard` |
| GET | `/admin/mesh-entities` |
| GET | `/admin/policy-modules` |
| GET | `/admin/review-destinations` |
| GET | `/admin/sources` |
| GET | `/admin/system-info` |
| GET | `/admin/workspaces` |
| GET | `/api/admin/api-keys` |
| POST | `/api/admin/api-keys` |
| PATCH | `/api/admin/api-keys/{name}` |
| GET | `/api/admin/api-keys/{name}/grants` |
| POST | `/api/admin/api-keys/{name}/grants/catalog` |
| DELETE | `/api/admin/api-keys/{name}/grants/catalog/{grant_id}` |
| POST | `/api/admin/api-keys/{name}/grants/ip` |
| DELETE | `/api/admin/api-keys/{name}/grants/ip/{grant_id}` |
| POST | `/api/admin/api-keys/{name}/quarantine` |
| POST | `/api/admin/api-keys/{name}/revoke` |
| POST | `/api/admin/api-keys/{name}/rotate` |
| POST | `/api/admin/api-keys/{name}/unquarantine` |
| GET | `/api/admin/api-keys/{name}/usage` |
| GET | `/api/admin/audit-sinks` |
| POST | `/api/admin/audit-sinks` |
| GET | `/api/admin/audit-sinks/recent-events` |
| DELETE | `/api/admin/audit-sinks/{sink_id}` |
| PATCH | `/api/admin/audit-sinks/{sink_id}` |
| POST | `/api/admin/audit-sinks/{sink_id}/test` |
| GET | `/api/admin/cdf-subscriptions` |
| POST | `/api/admin/cdf-subscriptions` |
| POST | `/api/admin/cdf-subscriptions/run-now` |
| DELETE | `/api/admin/cdf-subscriptions/{subscription_id}` |
| POST | `/api/admin/cdf-subscriptions/{subscription_id}/toggle` |
| GET | `/api/admin/coedit-bus/status` |
| GET | `/api/admin/domains` |
| POST | `/api/admin/domains` |
| PATCH | `/api/admin/domains/{domain_id}` |
| POST | `/api/admin/domains/{domain_id}/archive` |
| GET | `/api/admin/domains/{domain_id}/members` |
| POST | `/api/admin/domains/{domain_id}/members` |
| DELETE | `/api/admin/domains/{domain_id}/members/{user_id}` |
| PATCH | `/api/admin/domains/{domain_id}/members/{user_id}` |
| POST | `/api/admin/entity-discovery/run-now` |
| GET | `/api/admin/expected-producers` |
| POST | `/api/admin/expected-producers` |
| GET | `/api/admin/expected-producers/freshness` |
| DELETE | `/api/admin/expected-producers/{expectation_id}` |
| POST | `/api/admin/expected-producers/{expectation_id}/toggle` |
| GET | `/api/admin/external-writes` |
| POST | `/api/admin/external-writes/scan` |
| POST | `/api/admin/external-writes/{write_id}/acknowledge` |
| GET | `/api/admin/glossary` |
| POST | `/api/admin/glossary` |
| DELETE | `/api/admin/glossary/{term_id}` |
| GET | `/api/admin/glossary/{term_id}/bindings` |
| POST | `/api/admin/glossary/{term_id}/bindings` |
| DELETE | `/api/admin/glossary/{term_id}/bindings/{binding_id}` |
| GET | `/api/admin/governance/policy` |
| PUT | `/api/admin/governance/policy` |
| PUT | `/api/admin/governance/quota` |
| POST | `/api/admin/governance/scan` |
| GET | `/api/admin/ingest-sources` |
| GET | `/api/admin/ingest-sources/{source_id}/health` |
| GET | `/api/admin/mesh-entities` |
| POST | `/api/admin/mesh-entities` |
| DELETE | `/api/admin/mesh-entities/{entity_id}` |
| GET | `/api/admin/policy-modules` |
| POST | `/api/admin/policy-modules` |
| DELETE | `/api/admin/policy-modules/{module_id}` |
| PUT | `/api/admin/policy-modules/{module_id}` |
| GET | `/api/admin/policy-modules/{module_id}/decisions` |
| POST | `/api/admin/policy-modules/{module_id}/test` |
| GET | `/api/admin/repos` |
| POST | `/api/admin/repos` |
| DELETE | `/api/admin/repos/{repo_id}` |
| GET | `/api/admin/repos/{repo_id}` |
| POST | `/api/admin/repos/{repo_id}/rotate-webhook-secret` |
| POST | `/api/admin/repos/{repo_id}/secrets` |
| DELETE | `/api/admin/repos/{repo_id}/secrets/{kind}` |
| POST | `/api/admin/repos/{repo_id}/sync` |
| GET | `/api/admin/review-destinations` |
| POST | `/api/admin/review-destinations` |
| DELETE | `/api/admin/review-destinations/{dest_id}` |
| PATCH | `/api/admin/review-destinations/{dest_id}` |
| GET | `/api/admin/workspaces` |
| POST | `/api/admin/workspaces` |
| PATCH | `/api/admin/workspaces/{workspace_id}` |
| POST | `/api/admin/workspaces/{workspace_id}/archive` |
| GET | `/api/admin/workspaces/{workspace_id}/members` |
| POST | `/api/admin/workspaces/{workspace_id}/members` |
| DELETE | `/api/admin/workspaces/{workspace_id}/members/{user_id}` |
| PATCH | `/api/admin/workspaces/{workspace_id}/members/{user_id}` |
| GET | `/api/admin/workspaces/{workspace_id}/pins` |
| POST | `/api/admin/workspaces/{workspace_id}/pins` |
| DELETE | `/api/admin/workspaces/{workspace_id}/pins/{catalog_name}` |

## All routes

| Method | Path | Gate(s) | Status |
| --- | --- | --- | --- |
| GET | `/` | (login required, no role gate) | authenticated |
| GET | `/admin` | (login required, no role gate) | authenticated |
| GET | `/admin/api-keys` | (login required, no role gate) | authenticated |
| GET | `/admin/api-keys/{name}` | (login required, no role gate) | authenticated |
| GET | `/admin/audit` | (login required, no role gate) | authenticated |
| GET | `/admin/audit-sinks` | (login required, no role gate) | authenticated |
| GET | `/admin/audit/export` | (login required, no role gate) | authenticated |
| GET | `/admin/audit/export.tar.gz` | (login required, no role gate) | authenticated |
| GET | `/admin/audit/saved-filters` | (login required, no role gate) | authenticated |
| POST | `/admin/audit/saved-filters` | (login required, no role gate) | authenticated |
| DELETE | `/admin/audit/saved-filters/{filter_id}` | (login required, no role gate) | authenticated |
| PUT | `/admin/audit/saved-filters/{filter_id}` | (login required, no role gate) | authenticated |
| GET | `/admin/cdf-subscriptions` | (login required, no role gate) | authenticated |
| GET | `/admin/data-product-apply` | (login required, no role gate) | authenticated |
| GET | `/admin/domains` | (login required, no role gate) | authenticated |
| GET | `/admin/entity-discovery` | (login required, no role gate) | authenticated |
| GET | `/admin/external-writes` | (login required, no role gate) | authenticated |
| GET | `/admin/glossary` | (login required, no role gate) | authenticated |
| GET | `/admin/governance` | (login required, no role gate) | authenticated |
| GET | `/admin/mesh-dashboard` | (login required, no role gate) | authenticated |
| GET | `/admin/mesh-entities` | (login required, no role gate) | authenticated |
| GET | `/admin/policy-modules` | (login required, no role gate) | authenticated |
| GET | `/admin/review-destinations` | (login required, no role gate) | authenticated |
| GET | `/admin/sources` | (login required, no role gate) | authenticated |
| GET | `/admin/system-info` | (login required, no role gate) | authenticated |
| GET | `/admin/workspaces` | (login required, no role gate) | authenticated |
| GET | `/agent` | (login required, no role gate) | authenticated |
| GET | `/agent-reviews` | (login required, no role gate) | authenticated |
| GET | `/agent-reviews/{review_id}` | (login required, no role gate) | authenticated |
| GET | `/agents` | (login required, no role gate) | authenticated |
| GET | `/agents/{slug}` | (login required, no role gate) | authenticated |
| GET | `/alerts` | (login required, no role gate) | authenticated |
| GET | `/alerts/feed.atom` | (public allowlist) | public |
| GET | `/alerts/feed.json` | (public allowlist) | public |
| GET | `/alerts/{slug}` | (login required, no role gate) | authenticated |
| POST | `/api/2.0/sql/statements` | require_sql_execute | role-gated |
| GET | `/api/2.0/sql/statements/{statement_id}` | require_sql_execute | role-gated |
| POST | `/api/2.0/sql/statements/{statement_id}/cancel` | require_sql_execute | role-gated |
| GET | `/api/2.0/sql/statements/{statement_id}/result/chunks/{chunk_index}` | require_sql_execute | role-gated |
| GET | `/api/active-reviewer/queue` | (login required, no role gate) | authenticated |
| GET | `/api/admin/api-keys` | (login required, no role gate) | authenticated |
| POST | `/api/admin/api-keys` | (login required, no role gate) | authenticated |
| PATCH | `/api/admin/api-keys/{name}` | (login required, no role gate) | authenticated |
| GET | `/api/admin/api-keys/{name}/grants` | (login required, no role gate) | authenticated |
| POST | `/api/admin/api-keys/{name}/grants/catalog` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/api-keys/{name}/grants/catalog/{grant_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/api-keys/{name}/grants/ip` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/api-keys/{name}/grants/ip/{grant_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/api-keys/{name}/quarantine` | (login required, no role gate) | authenticated |
| POST | `/api/admin/api-keys/{name}/revoke` | (login required, no role gate) | authenticated |
| POST | `/api/admin/api-keys/{name}/rotate` | (login required, no role gate) | authenticated |
| POST | `/api/admin/api-keys/{name}/unquarantine` | (login required, no role gate) | authenticated |
| GET | `/api/admin/api-keys/{name}/usage` | (login required, no role gate) | authenticated |
| GET | `/api/admin/audit-sinks` | (login required, no role gate) | authenticated |
| POST | `/api/admin/audit-sinks` | (login required, no role gate) | authenticated |
| GET | `/api/admin/audit-sinks/recent-events` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/audit-sinks/{sink_id}` | (login required, no role gate) | authenticated |
| PATCH | `/api/admin/audit-sinks/{sink_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/audit-sinks/{sink_id}/test` | (login required, no role gate) | authenticated |
| GET | `/api/admin/cdf-subscriptions` | (login required, no role gate) | authenticated |
| POST | `/api/admin/cdf-subscriptions` | (login required, no role gate) | authenticated |
| POST | `/api/admin/cdf-subscriptions/run-now` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/cdf-subscriptions/{subscription_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/cdf-subscriptions/{subscription_id}/toggle` | (login required, no role gate) | authenticated |
| GET | `/api/admin/coedit-bus/status` | (login required, no role gate) | authenticated |
| GET | `/api/admin/domains` | (login required, no role gate) | authenticated |
| POST | `/api/admin/domains` | (login required, no role gate) | authenticated |
| PATCH | `/api/admin/domains/{domain_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/domains/{domain_id}/archive` | (login required, no role gate) | authenticated |
| GET | `/api/admin/domains/{domain_id}/members` | (login required, no role gate) | authenticated |
| POST | `/api/admin/domains/{domain_id}/members` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/domains/{domain_id}/members/{user_id}` | (login required, no role gate) | authenticated |
| PATCH | `/api/admin/domains/{domain_id}/members/{user_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/entity-discovery/run-now` | (login required, no role gate) | authenticated |
| GET | `/api/admin/expected-producers` | (login required, no role gate) | authenticated |
| POST | `/api/admin/expected-producers` | (login required, no role gate) | authenticated |
| GET | `/api/admin/expected-producers/freshness` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/expected-producers/{expectation_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/expected-producers/{expectation_id}/toggle` | (login required, no role gate) | authenticated |
| GET | `/api/admin/external-writes` | (login required, no role gate) | authenticated |
| POST | `/api/admin/external-writes/scan` | (login required, no role gate) | authenticated |
| POST | `/api/admin/external-writes/{write_id}/acknowledge` | (login required, no role gate) | authenticated |
| GET | `/api/admin/glossary` | (login required, no role gate) | authenticated |
| POST | `/api/admin/glossary` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/glossary/{term_id}` | (login required, no role gate) | authenticated |
| GET | `/api/admin/glossary/{term_id}/bindings` | (login required, no role gate) | authenticated |
| POST | `/api/admin/glossary/{term_id}/bindings` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/glossary/{term_id}/bindings/{binding_id}` | (login required, no role gate) | authenticated |
| GET | `/api/admin/governance/policy` | (login required, no role gate) | authenticated |
| PUT | `/api/admin/governance/policy` | (login required, no role gate) | authenticated |
| PUT | `/api/admin/governance/quota` | (login required, no role gate) | authenticated |
| POST | `/api/admin/governance/scan` | (login required, no role gate) | authenticated |
| GET | `/api/admin/ingest-sources` | (login required, no role gate) | authenticated |
| GET | `/api/admin/ingest-sources/{source_id}/health` | (login required, no role gate) | authenticated |
| GET | `/api/admin/lens-providers` | require_admin | role-gated |
| POST | `/api/admin/lens-providers` | require_admin | role-gated |
| DELETE | `/api/admin/lens-providers/{provider}` | require_admin | role-gated |
| POST | `/api/admin/lens-providers/{provider}/test` | require_admin | role-gated |
| GET | `/api/admin/mesh-entities` | (login required, no role gate) | authenticated |
| POST | `/api/admin/mesh-entities` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/mesh-entities/{entity_id}` | (login required, no role gate) | authenticated |
| GET | `/api/admin/policy-modules` | (login required, no role gate) | authenticated |
| POST | `/api/admin/policy-modules` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/policy-modules/{module_id}` | (login required, no role gate) | authenticated |
| PUT | `/api/admin/policy-modules/{module_id}` | (login required, no role gate) | authenticated |
| GET | `/api/admin/policy-modules/{module_id}/decisions` | (login required, no role gate) | authenticated |
| POST | `/api/admin/policy-modules/{module_id}/test` | (login required, no role gate) | authenticated |
| GET | `/api/admin/repos` | (login required, no role gate) | authenticated |
| POST | `/api/admin/repos` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/repos/{repo_id}` | (login required, no role gate) | authenticated |
| GET | `/api/admin/repos/{repo_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/repos/{repo_id}/rotate-webhook-secret` | (login required, no role gate) | authenticated |
| POST | `/api/admin/repos/{repo_id}/secrets` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/repos/{repo_id}/secrets/{kind}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/repos/{repo_id}/sync` | (login required, no role gate) | authenticated |
| GET | `/api/admin/review-destinations` | (login required, no role gate) | authenticated |
| POST | `/api/admin/review-destinations` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/review-destinations/{dest_id}` | (login required, no role gate) | authenticated |
| PATCH | `/api/admin/review-destinations/{dest_id}` | (login required, no role gate) | authenticated |
| GET | `/api/admin/workspaces` | (login required, no role gate) | authenticated |
| POST | `/api/admin/workspaces` | (login required, no role gate) | authenticated |
| PATCH | `/api/admin/workspaces/{workspace_id}` | (login required, no role gate) | authenticated |
| POST | `/api/admin/workspaces/{workspace_id}/archive` | (login required, no role gate) | authenticated |
| GET | `/api/admin/workspaces/{workspace_id}/members` | (login required, no role gate) | authenticated |
| POST | `/api/admin/workspaces/{workspace_id}/members` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/workspaces/{workspace_id}/members/{user_id}` | (login required, no role gate) | authenticated |
| PATCH | `/api/admin/workspaces/{workspace_id}/members/{user_id}` | (login required, no role gate) | authenticated |
| GET | `/api/admin/workspaces/{workspace_id}/pins` | (login required, no role gate) | authenticated |
| POST | `/api/admin/workspaces/{workspace_id}/pins` | (login required, no role gate) | authenticated |
| DELETE | `/api/admin/workspaces/{workspace_id}/pins/{catalog_name}` | (login required, no role gate) | authenticated |
| POST | `/api/agent-reviews` | (login required, no role gate) | authenticated |
| GET | `/api/agent-reviews/latest` | (login required, no role gate) | authenticated |
| GET | `/api/agent-reviews/{review_id}` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs` | (login required, no role gate) | authenticated |
| POST | `/api/agent-runs` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/diff` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/operations` | (login required, no role gate) | authenticated |
| POST | `/api/agent-runs/{run_id}/approve` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/{run_id}/audit/column-lineage` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/{run_id}/audit/external-writes` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/{run_id}/audit/lineage` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/{run_id}/audit/rejects` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/{run_id}/audit/value-changes` | (login required, no role gate) | authenticated |
| POST | `/api/agent-runs/{run_id}/deny` | (login required, no role gate) | authenticated |
| POST | `/api/agent-runs/{run_id}/finish` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/{run_id}/full` | (login required, no role gate) | authenticated |
| POST | `/api/agent-runs/{run_id}/rewrite-attempt` | (login required, no role gate) | authenticated |
| GET | `/api/agent-runs/{run_id}/summary` | (login required, no role gate) | authenticated |
| POST | `/api/agent-runs/{run_id}/tool-call` | (login required, no role gate) | authenticated |
| GET | `/api/agents` | (login required, no role gate) | authenticated |
| POST | `/api/agents` | (login required, no role gate) | authenticated |
| GET | `/api/agents/{agent_id}/authored-cells` | (login required, no role gate) | authenticated |
| GET | `/api/agents/{slug}/profile` | (login required, no role gate) | authenticated |
| POST | `/api/agents/{slug}/verify` | (login required, no role gate) | authenticated |
| GET | `/api/alerts` | (login required, no role gate) | authenticated |
| POST | `/api/alerts` | (login required, no role gate) | authenticated |
| DELETE | `/api/alerts/{slug}` | (login required, no role gate) | authenticated |
| GET | `/api/alerts/{slug}` | (login required, no role gate) | authenticated |
| PATCH | `/api/alerts/{slug}` | (login required, no role gate) | authenticated |
| POST | `/api/alerts/{slug}/destinations` | (login required, no role gate) | authenticated |
| DELETE | `/api/alerts/{slug}/destinations/{destination_id}` | (login required, no role gate) | authenticated |
| GET | `/api/audit/anomalies` | (login required, no role gate) | authenticated |
| POST | `/api/audit/anomaly-acks` | (login required, no role gate) | authenticated |
| DELETE | `/api/audit/anomaly-acks/{ack_id}` | (login required, no role gate) | authenticated |
| GET | `/api/audit/by-table` | (login required, no role gate) | authenticated |
| GET | `/api/audit/cdf-events` | (login required, no role gate) | authenticated |
| GET | `/api/audit/cdf-subscriptions` | (login required, no role gate) | authenticated |
| GET | `/api/audit/history` | (login required, no role gate) | authenticated |
| GET | `/api/audit/inbox` | (login required, no role gate) | authenticated |
| POST | `/api/audit/pii/reveal` | (login required, no role gate) | authenticated |
| GET | `/api/audit/principal-summary` | (login required, no role gate) | authenticated |
| GET | `/api/audit/search` | (login required, no role gate) | authenticated |
| GET | `/api/audit/summary` | (login required, no role gate) | authenticated |
| GET | `/api/audit/timeseries` | (login required, no role gate) | authenticated |
| GET | `/api/branches` | (login required, no role gate) | authenticated |
| GET | `/api/branches/{branch_fqn}` | (login required, no role gate) | authenticated |
| POST | `/api/branches/{branch_fqn}/discard` | (login required, no role gate) | authenticated |
| GET | `/api/branches/{branch_fqn}/preview-promote` | (login required, no role gate) | authenticated |
| POST | `/api/branches/{branch_fqn}/promote` | (login required, no role gate) | authenticated |
| GET | `/api/catalogs` | (login required, no role gate) | authenticated |
| POST | `/api/catalogs` | (login required, no role gate) | authenticated |
| PATCH | `/api/catalogs/{catalog_name}` | (login required, no role gate) | authenticated |
| GET | `/api/catalogs/{catalog_name}/schemas` | (login required, no role gate) | authenticated |
| PATCH | `/api/catalogs/{catalog_name}/schemas/{schema_name}` | (login required, no role gate) | authenticated |
| GET | `/api/catalogs/{catalog_name}/schemas/{schema_name}/tables` | (login required, no role gate) | authenticated |
| GET | `/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}` | (login required, no role gate) | authenticated |
| GET | `/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/preview` | (login required, no role gate) | authenticated |
| GET | `/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/stats` | (login required, no role gate) | authenticated |
| POST | `/api/catalogs/{catalog_name}/sync` | (login required, no role gate) | authenticated |
| GET | `/api/connections` | admin_uc | role-gated |
| POST | `/api/connections` | admin_uc | role-gated |
| DELETE | `/api/connections/{name}` | admin_uc | role-gated |
| GET | `/api/connections/{name}` | admin_uc | role-gated |
| PATCH | `/api/connections/{name}` | admin_uc | role-gated |
| POST | `/api/contracts/draft` | (login required, no role gate) | authenticated |
| GET | `/api/contracts/drafts` | (login required, no role gate) | authenticated |
| POST | `/api/contracts/drafts/{draft_id}/discard` | (login required, no role gate) | authenticated |
| POST | `/api/contracts/drafts/{draft_id}/promote` | (login required, no role gate) | authenticated |
| POST | `/api/contracts/save` | (login required, no role gate) | authenticated |
| GET | `/api/conventions` | (login required, no role gate) | authenticated |
| GET | `/api/cost/by-consumer` | (login required, no role gate) | authenticated |
| GET | `/api/cost/by-product` | (login required, no role gate) | authenticated |
| GET | `/api/credentials` | admin_uc | role-gated |
| POST | `/api/credentials` | admin_uc | role-gated |
| DELETE | `/api/credentials/{name}` | admin_uc | role-gated |
| GET | `/api/credentials/{name}` | admin_uc | role-gated |
| PATCH | `/api/credentials/{name}` | admin_uc | role-gated |
| POST | `/api/csp-report` | (public allowlist) | public |
| GET | `/api/dashboards` | (login required, no role gate) | authenticated |
| POST | `/api/dashboards` | (login required, no role gate) | authenticated |
| GET | `/api/dashboards/tree` | (login required, no role gate) | authenticated |
| DELETE | `/api/dashboards/{slug}` | (login required, no role gate) | authenticated |
| PATCH | `/api/dashboards/{slug}` | (login required, no role gate) | authenticated |
| POST | `/api/dashboards/{slug}/refresh` | (login required, no role gate) | authenticated |
| GET | `/api/data-products` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/apply` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/candidates` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/candidates/{candidate_id}/dismiss` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/candidates/{candidate_id}/generate-draft` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/plan` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/recommendations` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/reload` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/trending` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/access-requests` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/access-requests` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/access-requests/status` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/access-requests/{request_id}/approve` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/access-requests/{request_id}/deny` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/active-reviewer` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/active-reviewer` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/active-reviewer/run-now` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/activity` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/ask/sessions` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/ask/sessions/{session_id}/messages` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/bitemporal-policy` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/classifications` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/classifications` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/classifications/{classification_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/comments` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/comments` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/comments/{comment_id}` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/comments/{comment_id}/accept-answer` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/comments/{comment_id}/reactions` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/comments/{comment_id}/reactions` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/comments/{comment_id}/reactions/{emoji}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/consumption-acknowledgements` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/consumption-acknowledgements/{event_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/contract-tests` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/contract-tests` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/contract-tests/run` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/contract-tests/{contract_test_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/contract-tests/{contract_test_id}/results` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/control/forget` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/control/forget-requests` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/diff` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/discovery` | (login required, no role gate) | authenticated |
| PATCH | `/api/data-products/{catalog}/{schema}/domain` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/endorsements` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/endorsements` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/endorsements/{endorsement_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/entities` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/entities` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/entities` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/entities` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/entities/{binding_id}` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/entities/{entity_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/entities/{entity_id}/links` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/entities/{entity_id}/links` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/entities/{entity_id}/links/{link_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/entities/{entity_id}/resolve` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/event-subscriptions` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/event-subscriptions` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/event-subscriptions/{subscription_id}` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/event-subscriptions/{subscription_id}/pause` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/event-subscriptions/{subscription_id}/resume` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/event-subscriptions/{subscription_id}/rewind` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/events` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/export` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/export` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/fixtures` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/fixtures` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/fixtures/{fixture_id}` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/follow` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/follow` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/followers` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/followers/count` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/forget-requests` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/forks` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/governance` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/heatmap` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/infrastructure` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/infrastructure` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/ingest-status` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/input-ports` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/input-ports` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/input-ports/{port_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/interop` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/joinable` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/lifecycle` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/lifecycle/propose` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/lifecycle/{target_slug}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/lineage` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/mesh-graph` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/output-ports` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/output-ports` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/output-ports/{port_id}` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/output-ports/{port_id}/bump` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/output-ports/{port_id}/diff` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/output-ports/{port_id}/versions` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/passport` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/passport/refresh` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/point-in-time-read` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/point-in-time-read` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/policy` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/policy` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/policy-modules` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/proposals` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/proposals` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/proposals/{proposal_id}/approve` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/proposals/{proposal_id}/reject` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/rating` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/rating` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/reactions` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/reactions` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/reactions/{emoji}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/readme` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/readme` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/readme/diff` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/readme/history` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/readme/v/{version_int}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/related` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/releases` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/releases.atom` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/reviews` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/reviews` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/reviews` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/semantic` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/semantic/concepts` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/semantic/concepts/{concept_id}` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/semantic/sample-sql` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/slo-evaluation` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/slos` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/slos` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/slos/{slo_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/statistics` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/topics` | (login required, no role gate) | authenticated |
| PUT | `/api/data-products/{catalog}/{schema}/topics` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/transformations` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/transformations` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/transformations/{transformation_id}` | (login required, no role gate) | authenticated |
| GET | `/api/data-products/{catalog}/{schema}/use-cases` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/use-cases` | (login required, no role gate) | authenticated |
| DELETE | `/api/data-products/{catalog}/{schema}/use-cases/{use_case_id}` | (login required, no role gate) | authenticated |
| POST | `/api/data-products/{catalog}/{schema}/use-cases/{use_case_id}/vote` | (login required, no role gate) | authenticated |
| POST | `/api/dataframe-studio/compile` | (login required, no role gate) | authenticated |
| POST | `/api/dataframe-studio/preview` | (login required, no role gate) | authenticated |
| POST | `/api/dataframe-studio/validate` | (login required, no role gate) | authenticated |
| POST | `/api/dbt/compile` | (login required, no role gate) | authenticated |
| GET | `/api/dbt/coverage` | (login required, no role gate) | authenticated |
| POST | `/api/dbt/deps` | (login required, no role gate) | authenticated |
| GET | `/api/dbt/manifest` | (login required, no role gate) | authenticated |
| POST | `/api/dbt/run` | (login required, no role gate) | authenticated |
| GET | `/api/dbt/runs` | (login required, no role gate) | authenticated |
| POST | `/api/dbt/test` | (login required, no role gate) | authenticated |
| GET | `/api/dbt/test-failures` | (login required, no role gate) | authenticated |
| GET | `/api/domains` | (login required, no role gate) | authenticated |
| GET | `/api/domains/{slug}` | (login required, no role gate) | authenticated |
| GET | `/api/dp/_picker` | (login required, no role gate) | authenticated |
| GET | `/api/dp/{dp_id}/canvas` | (login required, no role gate) | authenticated |
| POST | `/api/dp/{dp_id}/canvas` | (login required, no role gate) | authenticated |
| GET | `/api/dp/{dp_id}/canvas/diff` | (login required, no role gate) | authenticated |
| POST | `/api/dp/{dp_id}/canvas/ghost-diff` | (login required, no role gate) | authenticated |
| POST | `/api/dp/{dp_id}/canvas/materialize` | (login required, no role gate) | authenticated |
| POST | `/api/dp/{dp_id}/canvas/preview` | (login required, no role gate) | authenticated |
| POST | `/api/dp/{dp_id}/canvas/validate` | (login required, no role gate) | authenticated |
| GET | `/api/dp/{dp_id}/canvas/versions` | (login required, no role gate) | authenticated |
| GET | `/api/dp/{dp_id}/canvas/versions/{version}` | (login required, no role gate) | authenticated |
| POST | `/api/dp/{dp_id}/canvas/versions/{version}/pin` | (login required, no role gate) | authenticated |
| POST | `/api/dp/{dp_id}/canvas/versions/{version}/unpin` | (login required, no role gate) | authenticated |
| GET | `/api/effective-permissions/{securable_type}/{full_name:path}` | (login required, no role gate) | authenticated |
| GET | `/api/entity-link-candidates` | (login required, no role gate) | authenticated |
| POST | `/api/entity-link-candidates/{candidate_id}/accept` | (login required, no role gate) | authenticated |
| POST | `/api/entity-link-candidates/{candidate_id}/defer` | (login required, no role gate) | authenticated |
| POST | `/api/entity-link-candidates/{candidate_id}/reject` | (login required, no role gate) | authenticated |
| GET | `/api/external-locations` | admin_uc | role-gated |
| POST | `/api/external-locations` | admin_uc | role-gated |
| DELETE | `/api/external-locations/{name}` | admin_uc | role-gated |
| GET | `/api/external-locations/{name}` | admin_uc | role-gated |
| PATCH | `/api/external-locations/{name}` | admin_uc | role-gated |
| GET | `/api/feed` | (login required, no role gate) | authenticated |
| POST | `/api/feed/mute` | (login required, no role gate) | authenticated |
| POST | `/api/feed/mute-author` | (login required, no role gate) | authenticated |
| GET | `/api/feed/people` | (login required, no role gate) | authenticated |
| POST | `/api/feed/seen` | (login required, no role gate) | authenticated |
| POST | `/api/feed/signals/{signal_id}/ack` | (login required, no role gate) | authenticated |
| POST | `/api/feed/snooze` | (login required, no role gate) | authenticated |
| GET | `/api/feed/trending` | (login required, no role gate) | authenticated |
| POST | `/api/feed/unmute` | (login required, no role gate) | authenticated |
| GET | `/api/glossary` | (login required, no role gate) | authenticated |
| GET | `/api/glossary/{slug}` | (login required, no role gate) | authenticated |
| GET | `/api/glossary/{term_id}/graph` | (login required, no role gate) | authenticated |
| GET | `/api/glossary/{term_id}/relations` | (login required, no role gate) | authenticated |
| POST | `/api/glossary/{term_id}/relations` | (login required, no role gate) | authenticated |
| DELETE | `/api/glossary/{term_id}/relations/{relation_id}` | (login required, no role gate) | authenticated |
| GET | `/api/health/backends` | (login required, no role gate) | authenticated |
| POST | `/api/hermes/start` | (login required, no role gate) | authenticated |
| GET | `/api/hermes/status` | (login required, no role gate) | authenticated |
| POST | `/api/hermes/stop` | (login required, no role gate) | authenticated |
| POST | `/api/ingest/probe` | (login required, no role gate) | authenticated |
| GET | `/api/ingest/sources` | (login required, no role gate) | authenticated |
| POST | `/api/ingest/sources` | (login required, no role gate) | authenticated |
| DELETE | `/api/ingest/sources/{source_id}` | (login required, no role gate) | authenticated |
| GET | `/api/ingest/sources/{source_id}` | (login required, no role gate) | authenticated |
| PATCH | `/api/ingest/sources/{source_id}` | (login required, no role gate) | authenticated |
| POST | `/api/ingest/sources/{source_id}/mappings` | (login required, no role gate) | authenticated |
| POST | `/api/ingest/sources/{source_id}/pulls` | (login required, no role gate) | authenticated |
| GET | `/api/ingest/sources/{source_id}/runs` | (login required, no role gate) | authenticated |
| PUT | `/api/ingest/sources/{source_id}/schedule` | (login required, no role gate) | authenticated |
| GET | `/api/ingest/sources/{source_id}/tables` | (login required, no role gate) | authenticated |
| GET | `/api/issues` | (login required, no role gate) | authenticated |
| GET | `/api/issues/{issue_id}` | (login required, no role gate) | authenticated |
| PATCH | `/api/issues/{issue_id}` | (login required, no role gate) | authenticated |
| POST | `/api/issues/{issue_id}/close` | (login required, no role gate) | authenticated |
| POST | `/api/issues/{issue_id}/reopen` | (login required, no role gate) | authenticated |
| GET | `/api/jobs` | (login required, no role gate) | authenticated |
| POST | `/api/jobs` | (login required, no role gate) | authenticated |
| GET | `/api/jobs/{job_id}/_kinds` | (login required, no role gate) | authenticated |
| GET | `/api/jobs/{job_id}/canvas` | (login required, no role gate) | authenticated |
| POST | `/api/jobs/{job_id}/canvas` | (login required, no role gate) | authenticated |
| GET | `/api/jobs/{job_id}/canvas/run-status` | (login required, no role gate) | authenticated |
| POST | `/api/jobs/{job_id}/canvas/validate` | (login required, no role gate) | authenticated |
| POST | `/api/jobs/{job_id}/pause` | (login required, no role gate) | authenticated |
| POST | `/api/jobs/{job_id}/run` | (login required, no role gate) | authenticated |
| GET | `/api/jobs/{job_id}/runs` | (login required, no role gate) | authenticated |
| GET | `/api/jobs/{job_id}/runs/{run_id}/logs` | (login required, no role gate) | authenticated |
| GET | `/api/jobs/{job_id}/runs/{run_id}/tasks` | (login required, no role gate) | authenticated |
| GET | `/api/jobs/{job_id}/tasks` | (login required, no role gate) | authenticated |
| POST | `/api/jobs/{job_id}/unpause` | (login required, no role gate) | authenticated |
| GET | `/api/lens/pinned` | require_analyst | role-gated |
| POST | `/api/lens/pinned` | require_analyst | role-gated |
| DELETE | `/api/lens/pinned/{slug}` | require_analyst | role-gated |
| GET | `/api/lens/pinned/{slug}` | require_analyst | role-gated |
| GET | `/api/lens/pinned/{slug}/view` | require_analyst | role-gated |
| GET | `/api/lens/provenance` | require_analyst | role-gated |
| GET | `/api/lens/sessions` | require_analyst | role-gated |
| POST | `/api/lens/sessions` | require_analyst | role-gated |
| DELETE | `/api/lens/sessions/{session_id}` | require_analyst | role-gated |
| GET | `/api/lens/sessions/{session_id}/messages` | require_analyst | role-gated |
| POST | `/api/lens/sessions/{session_id}/messages` | require_analyst | role-gated |
| GET | `/api/lineage/column-trace` | (login required, no role gate) | authenticated |
| POST | `/api/lineage/openlineage` | (login required, no role gate) | authenticated |
| GET | `/api/lineage/query/clusters` | (login required, no role gate) | authenticated |
| GET | `/api/lineage/query/downstream` | (login required, no role gate) | authenticated |
| GET | `/api/lineage/query/path` | (login required, no role gate) | authenticated |
| GET | `/api/lineage/query/upstream` | (login required, no role gate) | authenticated |
| GET | `/api/lineage/row-at-version` | (login required, no role gate) | authenticated |
| GET | `/api/lineage/row-trace` | (login required, no role gate) | authenticated |
| GET | `/api/lineage/value-changes` | (login required, no role gate) | authenticated |
| GET | `/api/lineage/{full_name:path}` | (login required, no role gate) | authenticated |
| GET | `/api/me` | (login required, no role gate) | authenticated |
| GET | `/api/me/feed-token` | (login required, no role gate) | authenticated |
| POST | `/api/me/feed-token/rotate` | (login required, no role gate) | authenticated |
| GET | `/api/me/settings` | (login required, no role gate) | authenticated |
| PUT | `/api/me/settings` | (login required, no role gate) | authenticated |
| GET | `/api/me/subscriptions` | (login required, no role gate) | authenticated |
| POST | `/api/me/subscriptions` | (login required, no role gate) | authenticated |
| DELETE | `/api/me/subscriptions/{sub_id}` | (login required, no role gate) | authenticated |
| PUT | `/api/me/subscriptions/{sub_id}` | (login required, no role gate) | authenticated |
| POST | `/api/memory/{agent_id}/branch` | (login required, no role gate) | authenticated |
| GET | `/api/memory/{agent_id}/recall` | (login required, no role gate) | authenticated |
| POST | `/api/memory/{agent_id}/replay` | (login required, no role gate) | authenticated |
| GET | `/api/mesh/canvas` | (login required, no role gate) | authenticated |
| POST | `/api/mesh/canvas` | (login required, no role gate) | authenticated |
| GET | `/api/mesh/canvas/picker/{workspace_slug}` | (login required, no role gate) | authenticated |
| POST | `/api/mesh/canvas/validate` | (login required, no role gate) | authenticated |
| GET | `/api/mesh/entities` | (login required, no role gate) | authenticated |
| GET | `/api/mesh/graph` | (login required, no role gate) | authenticated |
| GET | `/api/mesh/health` | (login required, no role gate) | authenticated |
| GET | `/api/mesh/health/full` | (login required, no role gate) | authenticated |
| POST | `/api/mesh/slo-scan` | (login required, no role gate) | authenticated |
| GET | `/api/mesh/trace/{correlation_id}` | (login required, no role gate) | authenticated |
| GET | `/api/ml/table-relations` | (login required, no role gate) | authenticated |
| GET | `/api/models` | (login required, no role gate) | authenticated |
| GET | `/api/models/{full_name}` | (login required, no role gate) | authenticated |
| GET | `/api/models/{full_name}/lineage` | (login required, no role gate) | authenticated |
| GET | `/api/models/{full_name}/predictions` | (login required, no role gate) | authenticated |
| POST | `/api/models/{full_name}/promote` | (login required, no role gate) | authenticated |
| GET | `/api/models/{full_name}/promotion` | (login required, no role gate) | authenticated |
| GET | `/api/models/{full_name}/runs` | (login required, no role gate) | authenticated |
| GET | `/api/models/{full_name}/versions/{version}` | (login required, no role gate) | authenticated |
| GET | `/api/notebook/chat/cell/{cell_uuid}/explanations` | (login required, no role gate) | authenticated |
| POST | `/api/notebook/chat/proposals/{proposal_id}/accept` | (login required, no role gate) | authenticated |
| POST | `/api/notebook/chat/proposals/{proposal_id}/discard` | (login required, no role gate) | authenticated |
| GET | `/api/notebook/chat/sequences/{proposal_id}` | (login required, no role gate) | authenticated |
| POST | `/api/notebook/chat/sequences/{proposal_id}/accept` | (login required, no role gate) | authenticated |
| POST | `/api/notebook/chat/sequences/{proposal_id}/discard` | (login required, no role gate) | authenticated |
| POST | `/api/notebook/chat/{chat_session_id}/propose-sequence` | (login required, no role gate) | authenticated |
| GET | `/api/notebook/chat/{chat_session_id}/sequences/pending` | (login required, no role gate) | authenticated |
| POST | `/api/notebook/chat/{editor_session_id}/explain-cell` | (login required, no role gate) | authenticated |
| POST | `/api/notebook/chat/{editor_session_id}/fix-cell` | (login required, no role gate) | authenticated |
| POST | `/api/notebook/chat/{editor_session_id}/propose-cell` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/attribution/bulk` | (login required, no role gate) | authenticated |
| DELETE | `/api/notebooks/branch` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/branch` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/branch` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/branch/history` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/branch/promote` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/cell-history` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/cell/attribution` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/cell/lineage` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/cell/lineage/bulk` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/create` | (login required, no role gate) | authenticated |
| DELETE | `/api/notebooks/delete` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/export.html` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/export.pdf` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/facts` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/facts` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/facts/bulk` | (login required, no role gate) | authenticated |
| DELETE | `/api/notebooks/facts/{fact_uuid}` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/facts/{fact_uuid}` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/from-template` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/inspect` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/jobs` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/load` | (login required, no role gate) | authenticated |
| DELETE | `/api/notebooks/permissions` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/permissions` | (login required, no role gate) | authenticated |
| PUT | `/api/notebooks/permissions` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/rename` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/render-markdown` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/replay` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/replay/{replay_uuid}` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/replay/{replay_uuid}/diff` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/replay/{replay_uuid}/finish` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/replays` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/revisions` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/revisions` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/revisions/diff` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/revisions/{revision_uuid}` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/revisions/{revision_uuid}/signature` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/run-once` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/save` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/shares` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/shares` | (login required, no role gate) | authenticated |
| DELETE | `/api/notebooks/shares/{share_uuid}` | (login required, no role gate) | authenticated |
| PATCH | `/api/notebooks/shares/{share_uuid}` | (login required, no role gate) | authenticated |
| DELETE | `/api/notebooks/tags` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/tags` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/tags` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/tags/bulk` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/templates` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/tree` | (login required, no role gate) | authenticated |
| DELETE | `/api/notebooks/widgets` | (login required, no role gate) | authenticated |
| GET | `/api/notebooks/widgets` | (login required, no role gate) | authenticated |
| PUT | `/api/notebooks/widgets` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/widgets/resolve` | (login required, no role gate) | authenticated |
| POST | `/api/notebooks/{notebook_id}/coedit/agent-presence` | (login required, no role gate) | authenticated |
| GET | `/api/notifications` | (login required, no role gate) | authenticated |
| POST | `/api/notifications/mark-all-read` | (login required, no role gate) | authenticated |
| POST | `/api/notifications/read-all` | (login required, no role gate) | authenticated |
| GET | `/api/notifications/stream` | (login required, no role gate) | authenticated |
| GET | `/api/notifications/unread-count` | (login required, no role gate) | authenticated |
| POST | `/api/notifications/{notification_id}/read` | (login required, no role gate) | authenticated |
| POST | `/api/notifications/{notification_id}/read` | (login required, no role gate) | authenticated |
| GET | `/api/permissions/{securable_type}/{full_name:path}` | (login required, no role gate) | authenticated |
| PATCH | `/api/permissions/{securable_type}/{full_name:path}` | (login required, no role gate) | authenticated |
| POST | `/api/pql/autoload` | (login required, no role gate) | authenticated |
| POST | `/api/pql/delete` | (login required, no role gate) | authenticated |
| POST | `/api/pql/drop_table` | (login required, no role gate) | authenticated |
| GET | `/api/pql/lineage` | (login required, no role gate) | authenticated |
| POST | `/api/pql/merge` | (login required, no role gate) | authenticated |
| GET | `/api/pql/primitives` | (login required, no role gate) | authenticated |
| GET | `/api/pql/target-state` | (login required, no role gate) | authenticated |
| POST | `/api/pql/training/log` | (login required, no role gate) | authenticated |
| POST | `/api/pql/update` | (login required, no role gate) | authenticated |
| POST | `/api/pql/write_table` | (login required, no role gate) | authenticated |
| GET | `/api/queries` | (login required, no role gate) | authenticated |
| GET | `/api/queries/{history_id}` | (login required, no role gate) | authenticated |
| PATCH | `/api/queries/{history_id}/chart-config` | (login required, no role gate) | authenticated |
| DELETE | `/api/recents` | (login required, no role gate) | authenticated |
| GET | `/api/recents` | (login required, no role gate) | authenticated |
| GET | `/api/runs` | (login required, no role gate) | authenticated |
| GET | `/api/runs/{run_id}/graph` | (login required, no role gate) | authenticated |
| GET | `/api/runs/{run_id}/ml-context` | (login required, no role gate) | authenticated |
| POST | `/api/runs/{run_id}/rollback` | (login required, no role gate) | authenticated |
| GET | `/api/runs/{run_id}/rollback-preview` | (login required, no role gate) | authenticated |
| GET | `/api/saved-audit-queries` | (login required, no role gate) | authenticated |
| POST | `/api/saved-audit-queries` | (login required, no role gate) | authenticated |
| DELETE | `/api/saved-audit-queries/{slug}` | (login required, no role gate) | authenticated |
| GET | `/api/saved-audit-queries/{slug}` | (login required, no role gate) | authenticated |
| PATCH | `/api/saved-audit-queries/{slug}` | (login required, no role gate) | authenticated |
| GET | `/api/saved-audit-queries/{slug}/export.csv` | (login required, no role gate) | authenticated |
| GET | `/api/saved-audit-queries/{slug}/export.json` | (login required, no role gate) | authenticated |
| POST | `/api/saved-audit-queries/{slug}/run` | (login required, no role gate) | authenticated |
| GET | `/api/saved-queries` | (login required, no role gate) | authenticated |
| POST | `/api/saved-queries` | (login required, no role gate) | authenticated |
| DELETE | `/api/saved-queries/{slug}` | (login required, no role gate) | authenticated |
| GET | `/api/saved-queries/{slug}` | (login required, no role gate) | authenticated |
| PATCH | `/api/saved-queries/{slug}` | (login required, no role gate) | authenticated |
| GET | `/api/search` | (login required, no role gate) | authenticated |
| GET | `/api/settings/notifications` | (login required, no role gate) | authenticated |
| PUT | `/api/settings/notifications` | (login required, no role gate) | authenticated |
| GET | `/api/social/notebook_cell/_bulk_counts` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/comments` | (login required, no role gate) | authenticated |
| POST | `/api/social/{kind}/{ref:path}/comments` | (login required, no role gate) | authenticated |
| DELETE | `/api/social/{kind}/{ref:path}/comments/{comment_id}` | (login required, no role gate) | authenticated |
| POST | `/api/social/{kind}/{ref:path}/comments/{comment_id}/accept-answer` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions` | (login required, no role gate) | authenticated |
| POST | `/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions` | (login required, no role gate) | authenticated |
| DELETE | `/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions/{emoji}` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/endorsements` | (login required, no role gate) | authenticated |
| POST | `/api/social/{kind}/{ref:path}/endorsements` | (login required, no role gate) | authenticated |
| DELETE | `/api/social/{kind}/{ref:path}/endorsements/{endorsement_id}` | (login required, no role gate) | authenticated |
| DELETE | `/api/social/{kind}/{ref:path}/follow` | (login required, no role gate) | authenticated |
| POST | `/api/social/{kind}/{ref:path}/follow` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/followers` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/followers/count` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/reactions` | (login required, no role gate) | authenticated |
| POST | `/api/social/{kind}/{ref:path}/reactions` | (login required, no role gate) | authenticated |
| DELETE | `/api/social/{kind}/{ref:path}/reactions/{emoji}` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/readme` | (login required, no role gate) | authenticated |
| PUT | `/api/social/{kind}/{ref:path}/readme` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/readme/diff` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/readme/history` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/readme/v/{version_int}` | (login required, no role gate) | authenticated |
| DELETE | `/api/social/{kind}/{ref:path}/reviews` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/reviews` | (login required, no role gate) | authenticated |
| PUT | `/api/social/{kind}/{ref:path}/reviews` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/reviews/{review_id}/reactions` | (login required, no role gate) | authenticated |
| POST | `/api/social/{kind}/{ref:path}/reviews/{review_id}/reactions` | (login required, no role gate) | authenticated |
| DELETE | `/api/social/{kind}/{ref:path}/reviews/{review_id}/reactions/{emoji}` | (login required, no role gate) | authenticated |
| DELETE | `/api/social/{kind}/{ref:path}/star` | (login required, no role gate) | authenticated |
| GET | `/api/social/{kind}/{ref:path}/star` | (login required, no role gate) | authenticated |
| POST | `/api/social/{kind}/{ref:path}/star` | (login required, no role gate) | authenticated |
| GET | `/api/social/{parent_kind}/{parent_ref:path}/issues` | (login required, no role gate) | authenticated |
| POST | `/api/social/{parent_kind}/{parent_ref:path}/issues` | (login required, no role gate) | authenticated |
| POST | `/api/sql/builder/build` | (login required, no role gate) | authenticated |
| POST | `/api/sql/builder/columns` | (login required, no role gate) | authenticated |
| GET | `/api/sql/builder/operators` | (login required, no role gate) | authenticated |
| POST | `/api/sql/builder/parse` | (login required, no role gate) | authenticated |
| POST | `/api/sql/chat/proposals/{proposal_id}/accept` | (login required, no role gate) | authenticated |
| POST | `/api/sql/chat/proposals/{proposal_id}/discard` | (login required, no role gate) | authenticated |
| POST | `/api/sql/chat/{editor_session_id}/propose` | (login required, no role gate) | authenticated |
| POST | `/api/sql/execute` | (login required, no role gate) | authenticated |
| GET | `/api/sql/execute/{history_id}/download` | (login required, no role gate) | authenticated |
| POST | `/api/sql/execute/{query_id}/cancel` | (login required, no role gate) | authenticated |
| POST | `/api/sql/execute_batch` | (login required, no role gate) | authenticated |
| GET | `/api/sql/explain` | (login required, no role gate) | authenticated |
| POST | `/api/sql/vector_search` | (login required, no role gate) | authenticated |
| GET | `/api/sql/vector_search/indices` | (login required, no role gate) | authenticated |
| POST | `/api/sql/vector_search/indices` | (login required, no role gate) | authenticated |
| DELETE | `/api/sql/vector_search/indices/{index_id}` | (login required, no role gate) | authenticated |
| POST | `/api/tables/{full_name:path}/profile` | (login required, no role gate) | authenticated |
| DELETE | `/api/tables/{full_name:path}/stats` | (login required, no role gate) | authenticated |
| GET | `/api/tables/{full_name:path}/stats` | (login required, no role gate) | authenticated |
| GET | `/api/tables/{full_name}/preview-at-version` | (login required, no role gate) | authenticated |
| GET | `/api/tables/{full_name}/versions` | (login required, no role gate) | authenticated |
| GET | `/api/tags/{securable_type}/{full_name:path}` | (login required, no role gate) | authenticated |
| PATCH | `/api/tags/{securable_type}/{full_name:path}` | (login required, no role gate) | authenticated |
| GET | `/api/topics` | (login required, no role gate) | authenticated |
| POST | `/api/topics` | (login required, no role gate) | authenticated |
| GET | `/api/topics/{slug}` | (login required, no role gate) | authenticated |
| DELETE | `/api/topics/{slug}/follow` | (login required, no role gate) | authenticated |
| POST | `/api/topics/{slug}/follow` | (login required, no role gate) | authenticated |
| GET | `/api/tree` | (login required, no role gate) | authenticated |
| GET | `/api/tree/search` | (login required, no role gate) | authenticated |
| GET | `/api/users/search` | (login required, no role gate) | authenticated |
| DELETE | `/api/users/{user_id}/follow` | (login required, no role gate) | authenticated |
| POST | `/api/users/{user_id}/follow` | (login required, no role gate) | authenticated |
| GET | `/api/users/{user_id}/followers` | (login required, no role gate) | authenticated |
| GET | `/api/users/{user_id}/following` | (login required, no role gate) | authenticated |
| GET | `/api/users/{user_id}/profile` | (login required, no role gate) | authenticated |
| PUT | `/api/users/{user_id}/profile` | (login required, no role gate) | authenticated |
| GET | `/api/users/{user_id}/stars` | (login required, no role gate) | authenticated |
| GET | `/api/views` | (login required, no role gate) | authenticated |
| POST | `/api/views` | (login required, no role gate) | authenticated |
| DELETE | `/api/views/{slug}` | (login required, no role gate) | authenticated |
| GET | `/api/views/{slug}` | (login required, no role gate) | authenticated |
| PATCH | `/api/views/{slug}` | (login required, no role gate) | authenticated |
| POST | `/api/views/{slug}/run` | (login required, no role gate) | authenticated |
| POST | `/api/volumes/{full_name:path}/convert-to-delta` | admin_uc | role-gated |
| GET | `/api/volumes/{full_name:path}/files` | (login required, no role gate) | authenticated |
| POST | `/api/volumes/{full_name:path}/files` | (login required, no role gate) | authenticated |
| DELETE | `/api/volumes/{full_name}/files/{path:path}` | (login required, no role gate) | authenticated |
| GET | `/api/workspaces/{slug}/activity` | (login required, no role gate) | authenticated |
| GET | `/api/workspaces/{slug}/pins` | (login required, no role gate) | authenticated |
| POST | `/api/workspaces/{slug}/pins` | (login required, no role gate) | authenticated |
| PATCH | `/api/workspaces/{slug}/pins/reorder` | (login required, no role gate) | authenticated |
| DELETE | `/api/workspaces/{slug}/pins/{social_target_id}` | (login required, no role gate) | authenticated |
| GET | `/api/workspaces/{workspace_id}/labels` | (login required, no role gate) | authenticated |
| POST | `/api/workspaces/{workspace_id}/labels` | (login required, no role gate) | authenticated |
| DELETE | `/api/workspaces/{workspace_id}/labels/{label_id}` | (login required, no role gate) | authenticated |
| GET | `/api/workspaces/{workspace_id}/milestones` | (login required, no role gate) | authenticated |
| POST | `/api/workspaces/{workspace_id}/milestones` | (login required, no role gate) | authenticated |
| DELETE | `/api/workspaces/{workspace_id}/milestones/{milestone_id}` | (login required, no role gate) | authenticated |
| GET | `/audit/by-table` | (login required, no role gate) | authenticated |
| GET | `/audit/by-table/{fqn:path}` | (login required, no role gate) | authenticated |
| GET | `/audit/inbox` | (login required, no role gate) | authenticated |
| GET | `/audit/queries` | (login required, no role gate) | authenticated |
| GET | `/audit/queries/{slug}` | (login required, no role gate) | authenticated |
| GET | `/audit/search` | (login required, no role gate) | authenticated |
| GET | `/auth/callback` | (public allowlist) | public |
| GET | `/auth/login` | (public allowlist) | public |
| POST | `/auth/login` | (public allowlist) | public |
| POST | `/auth/logout` | (public allowlist) | public |
| GET | `/auth/me` | (public allowlist) | public |
| GET | `/auth/register` | (public allowlist) | public |
| POST | `/auth/register` | (public allowlist) | public |
| GET | `/auth/sso` | (public allowlist) | public |
| POST | `/auth/switch-workspace` | (public allowlist) | public |
| GET | `/branches` | (login required, no role gate) | authenticated |
| GET | `/branches/{branch_fqn}` | (login required, no role gate) | authenticated |
| GET | `/canvas` | (login required, no role gate) | authenticated |
| GET | `/catalogs/{catalog_name}` | (login required, no role gate) | authenticated |
| GET | `/catalogs/{catalog_name}/schemas/{schema_name}` | (login required, no role gate) | authenticated |
| GET | `/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}` | (login required, no role gate) | authenticated |
| GET | `/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/columns/{column_name}/trace` | (login required, no role gate) | authenticated |
| GET | `/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/rows/{row_id}/trace` | (login required, no role gate) | authenticated |
| GET | `/connections` | admin_uc | role-gated |
| GET | `/connections/{name}` | admin_uc | role-gated |
| GET | `/credentials` | admin_uc | role-gated |
| GET | `/credentials/{name}` | admin_uc | role-gated |
| GET | `/dashboards` | (login required, no role gate) | authenticated |
| GET | `/dashboards/{slug}` | (login required, no role gate) | authenticated |
| GET | `/dashboards/{slug}/output` | (login required, no role gate) | authenticated |
| GET | `/data-products` | (login required, no role gate) | authenticated |
| GET | `/data-products/candidates` | (login required, no role gate) | authenticated |
| GET | `/data-products/followed` | (login required, no role gate) | authenticated |
| GET | `/data-products/trending` | (login required, no role gate) | authenticated |
| GET | `/data-products/{catalog}/{schema}` | (login required, no role gate) | authenticated |
| GET | `/dataframe-studio` | (login required, no role gate) | authenticated |
| GET | `/dbt` | (login required, no role gate) | authenticated |
| DELETE | `/dbt-docs/{path:path}` | (login required, no role gate) | authenticated |
| GET | `/dbt-docs/{path:path}` | (login required, no role gate) | authenticated |
| PATCH | `/dbt-docs/{path:path}` | (login required, no role gate) | authenticated |
| POST | `/dbt-docs/{path:path}` | (login required, no role gate) | authenticated |
| PUT | `/dbt-docs/{path:path}` | (login required, no role gate) | authenticated |
| GET | `/domains` | (login required, no role gate) | authenticated |
| GET | `/domains/{slug}` | (login required, no role gate) | authenticated |
| GET | `/dp/{dp_id}/canvas` | (login required, no role gate) | authenticated |
| GET | `/dp/{dp_id}/canvas/diff` | (login required, no role gate) | authenticated |
| GET | `/embed/notebook_share/{share_uuid}` | (public allowlist) | public |
| GET | `/embed/semantic_search/{table_fqn}` | (login required, no role gate) | authenticated |
| GET | `/external-locations` | admin_uc | role-gated |
| GET | `/external-locations/{name}` | admin_uc | role-gated |
| GET | `/feed` | (login required, no role gate) | authenticated |
| GET | `/glossary` | (login required, no role gate) | authenticated |
| GET | `/glossary/{slug}` | (login required, no role gate) | authenticated |
| GET | `/healthz` | (public allowlist) | public |
| GET | `/help` | (login required, no role gate) | authenticated |
| GET | `/hermes` | (login required, no role gate) | authenticated |
| DELETE | `/hermes/{path:path}` | (login required, no role gate) | authenticated |
| GET | `/hermes/{path:path}` | (login required, no role gate) | authenticated |
| PATCH | `/hermes/{path:path}` | (login required, no role gate) | authenticated |
| POST | `/hermes/{path:path}` | (login required, no role gate) | authenticated |
| PUT | `/hermes/{path:path}` | (login required, no role gate) | authenticated |
| GET | `/ingest/sources` | (login required, no role gate) | authenticated |
| GET | `/ingest/sources/new` | (login required, no role gate) | authenticated |
| GET | `/ingest/sources/{source_id}` | (login required, no role gate) | authenticated |
| GET | `/issues` | (login required, no role gate) | authenticated |
| GET | `/issues/{issue_id}` | (login required, no role gate) | authenticated |
| GET | `/jobs` | (login required, no role gate) | authenticated |
| GET | `/jobs/{job_id}` | (login required, no role gate) | authenticated |
| GET | `/jobs/{job_id}/dag` | (login required, no role gate) | authenticated |
| GET | `/jobs/{job_id}/runs/{run_id}/compare` | (login required, no role gate) | authenticated |
| GET | `/jobs/{job_id}/runs/{run_id}/notebook` | (login required, no role gate) | authenticated |
| GET | `/jobs/{job_id}/runs/{run_id}/notebook/download` | (login required, no role gate) | authenticated |
| GET | `/lens` | require_analyst | role-gated |
| GET | `/library/facts` | (login required, no role gate) | authenticated |
| GET | `/lineage` | (login required, no role gate) | authenticated |
| GET | `/mcp/health` | (public allowlist) | public |
| GET | `/mcp/info` | (public allowlist) | public |
| GET | `/me` | (login required, no role gate) | authenticated |
| GET | `/me/settings` | (login required, no role gate) | authenticated |
| GET | `/me/subscriptions` | (login required, no role gate) | authenticated |
| GET | `/memory/{agent_id}` | (login required, no role gate) | authenticated |
| GET | `/mesh` | (login required, no role gate) | authenticated |
| GET | `/mesh/canvas` | (login required, no role gate) | authenticated |
| GET | `/mesh/entities` | (login required, no role gate) | authenticated |
| GET | `/mesh/health` | (login required, no role gate) | authenticated |
| GET | `/metrics` | (login required, no role gate) | authenticated |
| GET | `/ml` | (login required, no role gate) | authenticated |
| DELETE | `/mlflow/{path:path}` | (login required, no role gate) | authenticated |
| GET | `/mlflow/{path:path}` | (login required, no role gate) | authenticated |
| PATCH | `/mlflow/{path:path}` | (login required, no role gate) | authenticated |
| POST | `/mlflow/{path:path}` | (login required, no role gate) | authenticated |
| PUT | `/mlflow/{path:path}` | (login required, no role gate) | authenticated |
| GET | `/models` | (login required, no role gate) | authenticated |
| GET | `/models/{full_name}` | (login required, no role gate) | authenticated |
| GET | `/models/{full_name}/compare` | (login required, no role gate) | authenticated |
| GET | `/new` | (login required, no role gate) | authenticated |
| GET | `/notebooks/edit/{path:path}` | (login required, no role gate) | authenticated |
| GET | `/notebooks/uuid/{notebook_uuid}` | (login required, no role gate) | authenticated |
| GET | `/notebooks/workspace` | (login required, no role gate) | authenticated |
| GET | `/notifications` | (login required, no role gate) | authenticated |
| GET | `/queries` | (login required, no role gate) | authenticated |
| GET | `/runs` | (login required, no role gate) | authenticated |
| GET | `/runs/{a}/diff/{b}` | (login required, no role gate) | authenticated |
| GET | `/runs/{run_id}` | (login required, no role gate) | authenticated |
| GET | `/settings/notifications` | (login required, no role gate) | authenticated |
| GET | `/share/notebook/{share_uuid}` | (public allowlist) | public |
| GET | `/sql` | (login required, no role gate) | authenticated |
| GET | `/static/css/style.css` | (public allowlist) | public |
| GET | `/static/js/{rel_path:path}` | (public allowlist) | public |
| GET | `/topics` | (login required, no role gate) | authenticated |
| GET | `/topics/{slug}` | (login required, no role gate) | authenticated |
| GET | `/users` | (login required, no role gate) | authenticated |
| GET | `/users/me` | (login required, no role gate) | authenticated |
| GET | `/users/{user_id}` | (login required, no role gate) | authenticated |
| GET | `/views` | (login required, no role gate) | authenticated |
| GET | `/views/new` | (login required, no role gate) | authenticated |
| GET | `/views/{slug}` | (login required, no role gate) | authenticated |
| GET | `/views/{slug}/embed` | (login required, no role gate) | authenticated |
| GET | `/volumes` | (login required, no role gate) | authenticated |
| GET | `/volumes/{full_name:path}` | (login required, no role gate) | authenticated |
| POST | `/webhook/git/{repo_id}` | (public allowlist) | public |
| GET | `/workspaces/{slug}` | (login required, no role gate) | authenticated |
