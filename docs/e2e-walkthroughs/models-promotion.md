# E2E walkthrough — Champion/Challenger model promotion (Sprint 21.6)

This playbook validates the supervisor-only promotion-hop UI added
in Sprint 21.6.  The vertical slice: an operator browses to a
registered model with two `READY` versions, promotes one to
champion through the modal, sees the champion-badge migrate, and
finds the promotion in the history list.

The walkthrough assumes the Sprint 21.5 e2e
([`models-tab.md`](models-tab.md)) has already produced a
`pql_test.mlflow_smoke.smoke_model` registered model with at least
two `READY` versions.

## Setup

```bash
# Terminal 1 — soyuz-catalog
cd ~/git/soyuz-catalog
uv run soyuz-catalog          # http://127.0.0.1:8080

# Terminal 2 — PointlesSQL
cd ~/git/PointlesSQL
uv run pointlessql            # http://127.0.0.1:8000
```

Login as the bootstrap admin user (admin scope passes
`require_supervisor`, which gates the promote endpoint).

## Step 1 — Open the model-detail page

Navigate to `http://127.0.0.1:8000/models/pql_test.mlflow_smoke.smoke_model`.

Expect: the 5-tab layout from Sprint 21.5 with one tab swapped:
the *Permissions* stub is gone, replaced by *Promotion*.

## Step 2 — Champion-badge on Versions tab

Click the *Versions* tab.

Expect: every `READY` row carries the version chip; one of them
(default = the highest-numbered `READY` version when no marker
exists) shows an additional warning-coloured `★ Champion` badge.

## Step 3 — Open the Promotion tab

Click *Promotion*.

Expect:

- *Current champion* card on the left says `Champion version: vN`,
  matching the badge from Step 2. No `Promoted by` / `Reason`
  rows because the model has no marker yet — they only appear
  after the first promotion.
- *Promote a challenger* card on the right lists every version
  with a `Promote` button on the `READY` rows. The current
  champion's button is disabled (and labelled with the same
  star-badge).

## Step 4 — Promote a challenger

Click `Promote` on the non-champion version (e.g. v1 if v2 was the
default champion).

Expect: the modal opens with the title `Promote v1 to champion`.

Type a reason — e.g. `Smoke-test rollback to v1`. The *Promote*
button is disabled until non-whitespace text is entered.

Click *Promote*.

Expect:

- The modal closes.
- The *Current champion* card refreshes to `v1`, the `Promoted by`
  field shows the cookie user's email, and the reason matches what
  you typed.
- The Versions table star-badge moves to v1 (page-level state).
- The history accordion now shows `1` entry.

## Step 5 — Promote back

Click `Promote` on v2 with reason `Restoring v2`.

Expect: champion swaps back to v2; history grows to 2 entries.
Newest entry first.

## Step 6 — Inspect the marker on soyuz

```bash
curl -s http://127.0.0.1:8080/api/2.1/unity-catalog/models/pql_test.mlflow_smoke.smoke_model | jq -r .comment
```

Expect: a JSON chunk containing `"_pql_promotion"` with
`champion_version`, `promoted_by`, `promoted_at`, `reason`, and
`previous_champion`.

If the model already had user prose before promotion, that prose
is preserved before the marker (chunks separated by `\n\n`).

## Step 7 — Permissions ladder (negative test)

Logout. Re-login as the second non-admin test user
(`nonadmin@test.com`).

Navigate back to `/models/pql_test.mlflow_smoke.smoke_model`. The
Promotion tab still renders (read-only browse), but clicking
`Promote` and submitting the modal should show the in-modal
error banner with the supervisor-scope rejection.

## Step 8 — AgentReview row in DB

```bash
sqlite3 ~/.local/share/pointlessql/auth.db \
  "SELECT id, kind, severity, summary_md FROM agent_reviews ORDER BY id DESC LIMIT 5"
```

Expect: at least 2 rows with `kind = "model_promotion"`,
`severity = "ok"`, and the summary mentions
`pql_test.mlflow_smoke.smoke_model`.

## Step 9 — CloudEvent envelope

If a webhook is configured at
`POINTLESSQL_AGENT_RUNS__WEBHOOK_URL`, the `pointlessql.model.promoted`
envelope arrives with `subject = "pql_test.mlflow_smoke.smoke_model@v2"`,
`source = "/pointlessql/agent_reviews/{review_id}"`, and
`data.previous_champion`. Without a configured webhook the
envelope is still returned in the API response body — confirm via
DevTools → Network → `/api/models/.../promote` → Response.

## Known limitations

- Aliases are stored only as a marker on the model's `comment`
  field. A first-class soyuz `model_aliases` table is deferred —
  the marker convention gives equivalent semantics today and
  a future one-shot script can re-emit markers as real catalog
  tags when soyuz ships them.
- The Promotion tab does not yet show the underlying MLflow
  metrics for each version side-by-side; for that flow use the
  Sprint 21.5.4 compare-view at `/models/.../compare?v1=…&v2=…`.
