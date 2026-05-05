# OIDC group → workspace + scope mapping

Phase 29.3 lets an OIDC IdP's group claim drive both **which workspace
a user lands in** and **which auditor / supervisor / admin scopes they
hold**, without minting a parallel API key. Empty / unset
configuration preserves the pre-29.3 default — every OIDC user lands
in the install-default workspace with no extra scopes.

## How it works

On every login, PointlesSQL:

1. Asks the IdP for the configured scopes (`openid email profile` by
   default; add `groups` to flow group memberships through).
2. Reads the configured `groups` claim from the userinfo response.
3. Looks up each group in the parsed mapping table.
4. Unions the scope grants across every matching group.
5. Picks the **first matching** mapping's `ws=` value as the user's
   `default_workspace_id` (later mappings don't override it).
6. Persists the raw groups list to `users.oidc_groups_json` for audit
   visibility — authz never reads this column at runtime.

Group changes at the IdP propagate at next login: the supervisor and
auditor flags are re-resolved every time, never sticky.

## Configuration

Three environment variables, all under the `POINTLESSQL_OIDC_*`
prefix.

| Variable | Default | Notes |
|---|---|---|
| `POINTLESSQL_OIDC_SCOPE` | `openid email profile` | Add `groups` (or your IdP's equivalent) to receive memberships. |
| `POINTLESSQL_OIDC_GROUPS_CLAIM_NAME` | `groups` | Override per IdP — Cognito uses `cognito:groups`, some Keycloak setups use `roles`. |
| `POINTLESSQL_OIDC_GROUP_MAP_RAW` | (empty) | The mapping table. Empty disables the feature. |

### `GROUP_MAP_RAW` format

Semicolon-separated entries, comma-separated fields per entry:

```
group_a:ws=N,scopes=admin|supervisor|auditor;group_b:ws=M,scopes=auditor
```

* `ws=` — optional; the workspace ID this mapping routes to. Omit to
  grant scopes only without changing the user's workspace.
* `scopes=` — optional; pipe-separated subset of `admin | supervisor
  | auditor`. Omit (or set to empty) to grant no scopes.

A degenerate entry with neither `ws=` nor `scopes=` is rejected at
startup.

## Worked example

```bash
export POINTLESSQL_OIDC_SCOPE="openid email profile groups"
export POINTLESSQL_OIDC_GROUPS_CLAIM_NAME="groups"
export POINTLESSQL_OIDC_GROUP_MAP_RAW="\
ops-admins:ws=1,scopes=admin;\
data-team:ws=2,scopes=supervisor;\
sec-auditors:ws=2,scopes=auditor|supervisor;\
warehouse-readers:scopes="
```

Resulting behaviour at login:

* A user in `ops-admins` lands in workspace 1 with full admin scope.
* A user in `data-team` lands in workspace 2 as a supervisor.
* A user in both `data-team` AND `sec-auditors` lands in workspace 2
  with the union of supervisor + auditor flags.
* A user only in `warehouse-readers` keeps their existing
  `default_workspace_id` (no `ws=`) and gains no scopes (empty
  `scopes=`) — the entry is a placeholder for "this group is known but
  carries no privilege".

## Asymmetric privilege ladder

Same rule as the API-key path (pinned in Sprint 19.1):

* `auditor` passes both `require_auditor` and `require_supervisor` —
  read-only audit mandate spans tenant-wide aggregates and per-run
  inspection.
* `supervisor` passes only `require_supervisor` — supervisor scope is
  run-scoped and would leak data the auditor mandate is the right
  shape for.
* `admin` passes everything (strictly stronger).

A user in two groups whose mappings both grant `auditor` and
`supervisor` ends up with both flags — the union, not the intersection.

## Limitations

* The mapping is install-global, not per-workspace.
* Auto-provisioning a new workspace from a previously-unseen group is
  out of scope — unmapped groups fall through to
  `default_workspace_id`.
* Edits require a service restart; runtime mutation lands in a
  follow-up sprint if needed.
* There is no admin UI for the mapping yet — operate via env var.

## Audit

Every login refreshes `users.oidc_groups_json`. Operators can grep the
table to see who is in which IdP groups today; the audit-cockpit
"principal summary" surface picks this up automatically.
