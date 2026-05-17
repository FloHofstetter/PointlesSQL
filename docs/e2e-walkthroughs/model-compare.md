# Model compare walkthrough

> **Mode:** `browser` · **Phase:** 21 · **Surface:** `/models/{full_name}/compare?v1=X&v2=Y`

Covers the side-by-side model-version comparison view that
landed with Phase 21.5: two cards with v1 + v2 metadata, a
metrics table with Δ + Δ% direction-classified (`better` /
`worse` / `neutral`), and params + tags diff cards (added /
removed / changed). Driven by the cross-link aggregator that
joins soyuz `MODEL_VERSION` securables with MLflow metric/param
rows on `mlflow_run_id`.

## Preconditions

- Stack up via `docker/docker-compose.yml` + `docker/docker-compose.e2e.yml`
  with `POINTLESSQL_MLFLOW_ENABLED=1`.
- [`auth.md`](auth.md) ran first — `admin@pql.test` is signed in.
- [`models-tab.md`](models-tab.md) ran first — at least 2
  versions of `demo.ml.churn_classifier` exist with metric
  rows (e.g. `auc`, `f1`, `recall`) and at least one
  changed param across versions.
- Browser: `--browser firefox` per CLAUDE.md.

## Walkthrough

1. **Open compare from the model-detail page.**
   - Action: `browser_navigate('http://127.0.0.1:8000/models/demo.ml.churn_classifier')`.
   - Action: select `v1=1`, `v2=2` from the compare dropdowns
     (or click the `Compare v1 ↔ v2` link in the Versions card).
   - Assert: URL becomes
     `/models/demo.ml.churn_classifier/compare?v1=1&v2=2`.
   - Assert: page title is `Compare v1 vs v2 · demo.ml.churn_classifier`.

2. **Header + breadcrumbs.**
   - Assert: breadcrumbs show
     `Home › Models › demo.ml.churn_classifier ›
     Compare v1 ↔ v2`.
   - Assert: `<h1>` ends with `v1 ↔ v2` (en-em arrow plus
     version numbers).
   - Assert: a `Back to demo.ml.churn_classifier` button is
     visible and points to `/models/demo.ml.churn_classifier`.

3. **Metadata cards render symmetric data for v1 and v2.**
   - Assert: two `.col-md-6` cards in the first row, with headers
     `v1` and `v2`.
   - Assert: each `<dl>` lists `Status`, `MLflow Run`, `Source`.
   - Assert: the MLflow Run cell is a 16-char `<code>` followed
     by `…` if the run-id is truncated.

4. **Metrics table populates from cross-link aggregator.**
   - Assert: the Metrics card has a table with 5 columns:
     `Metric`, `v1`, `v2`, `Δ`, `Δ%`.
   - Assert: at least one row exists (e.g. `auc`); each metric
     name is a `<code>` and carries a small badge with the
     polarity classification (`higher_is_better` /
     `lower_is_better` / `neutral`).
   - Assert: numeric cells use `font-monospace small` formatting;
     missing values render as `—`.

5. **Δ direction colour-coding matches polarity.**
   - Action: identify a metric where `v2.value > v1.value`.
   - Assert: if the metric is `higher_is_better`, the Δ and Δ%
     cells carry class `text-success`; if
     `lower_is_better`, they carry `text-danger`.
   - Assert: where one of v1/v2 is missing, both Δ cells render
     as plain `—` without colour.

6. **Empty-metrics state.**
   - Setup: pick a model whose runs have no metrics (or rename a
     metric in the seed so the cross-link aggregator returns
     `metric_diff=[]`).
   - Assert: the Metrics card body reads
     `No metrics recorded for either run.` and there is no
     `<table>`.

7. **Params diff card — three sub-sections.**
   - Assert: the Params card contains up to three sub-sections:
     `Changed` (yellow heading), `Added in v2` (green),
     `Removed (only in v1)` (red).
   - Assert: each `Changed` row is a 3-column table:
     `Name`, `v1`, `v2`; param names are `<code>`.
   - Assert: when no diffs exist, the card body reads
     `No param differences.`.

8. **Tags diff mirrors the params layout.**
   - Assert: identical 3-section layout (Changed / Added /
     Removed) with the same colour cues.
   - Assert: when both versions carry no tags, the card body
     reads `No tag differences.`.

9. **Same-version compare returns a 400.**
   - Action: `browser_navigate('http://127.0.0.1:8000/models/demo.ml.churn_classifier/compare?v1=1&v2=1')`.
   - Assert: HTTP status is 400 (or 422); the error envelope
     surfaces `error_code=MODEL_COMPARE_SAME_VERSION` (or
     equivalent).

10. **Missing-version compare returns a 404.**
    - Action: `browser_navigate('http://127.0.0.1:8000/models/demo.ml.churn_classifier/compare?v1=99&v2=100')`.
    - Assert: HTTP status is 404; the page renders the standard
      404 template.

11. **Unauthenticated redirect.**
    - Action: log out (`/auth/logout`) and revisit the compare
      URL.
    - Assert: redirect to
      `/auth/login?next=/models/demo.ml.churn_classifier/compare?v1=1&v2=2`.

## Playwright MCP script

```text
1. browser_navigate /models/demo.ml.churn_classifier
2. browser_click "Compare v1 ↔ v2"
3. browser_wait_for "Metrics"
4. browser_evaluate ".col-md-6 .card-header" -> ["v1", "v2"]
5. browser_evaluate ".table tbody tr" .length >= 1
6. browser_navigate /models/demo.ml.churn_classifier/compare?v1=1&v2=1
   -> assert 400
```

## Found bugs

_None recorded yet — first replay is part of the Phase 41
Playwright-coverage pass._
