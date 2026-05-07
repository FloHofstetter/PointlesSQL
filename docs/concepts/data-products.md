# Data Products

A *data product* in PointlesSQL is the convention "this UC schema
is a named, owned, versioned bundle of tables".  The schema
metadata (steward, version, freshness SLA, expected per-table
schema) lives in a `pointlessql.yaml` file committed to the data
team's repo; the file is canonical (git-blame is the audit log).

PointlesSQL does **not** introduce a new UC entity.  A "data
product" is an opt-in property of an existing UC schema — turn on
the property by dropping a `pointlessql.yaml` declaring it; turn
it off by removing the file.

## Why bother?

Without the convention, a UC schema is just a folder of tables
that can drift in any direction.  With it:

- **Discovery.**  `/data-products` shows every product in the
  workspace, grouped by domain, with steward + version + SLA.
- **Contract enforcement.**  Every `pql.write` / `pql.merge` is
  diffed against the contract before any Delta IO.  A breaking
  change (missing required column, swapped type, dropped PK)
  raises `DataProductContractViolation` and the bad write never
  lands.
- **Freshness alerts.**  A scanner walks every product whose
  `sla_minutes` is set and emits a CloudEvent when the latest
  write across the product's tables falls behind the SLA.
- **Agent-readable.**  Five plugin tools surface discovery,
  contract inspection, live-diff and compliance history to LLM
  agents so an agent can sanity-check its frame schema *before*
  calling write.

## yaml shape

The grammar is deliberately small.  A complete contract:

```yaml
data_product:
  name: Sales Orders
  version: "1.2.0"
  description: |
    Curated orders facts joined with customer dim.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id,    type: long,      nullable: false}
        - {name: customer_id, type: long,      nullable: false}
        - {name: order_total, type: decimal,   nullable: true}
        - {name: ordered_at,  type: timestamp, nullable: false}
```

Top-level keys:

- **`name`** — human-readable product name.  Distinct from the
  UC schema name; the same UC schema could be re-named in
  product-speak (e.g. "Sales Orders" vs `sales_gold`).
- **`version`** — SemVer string (`major.minor.patch`).  The
  loader does not enforce SemVer arithmetic; the convention is
  "bump major when a contract change would break consumers".
- **`description`** — one-paragraph summary.
- **`catalog`** + **`schema`** — UC three-part identity (the
  table component is part of each entry under `tables`).
- **`steward_email`** — optional.  When the email matches a
  persisted `users` row, the loader sets the FK on the cache;
  otherwise the FK stays NULL and the UI falls back to a mailto
  link.
- **`sla_minutes`** — optional freshness SLA.  Products without
  one are skipped by the scanner.
- **`tables`** — per-table contract list.  Declaring fewer
  tables than the UC schema actually contains is fine — the
  enforcement hook treats undeclared tables as `no_contract`
  rather than refusing the write.

## Column types

The contract supports 11 types, designed to cover Delta's common
primitives without requiring authors to think in pyarrow logical
types:

| Type | Notes |
|---|---|
| `string` | UTF-8 text |
| `integer` | 32-bit signed |
| `long` | 64-bit signed |
| `double` | 64-bit float |
| `boolean` | true/false |
| `timestamp` | UTC |
| `date` | calendar date, no time |
| `decimal` | parametrised; the diff helper collapses precision/scale |
| `binary` | raw bytes |
| `array` | structured; not deeply diffed in v1 |
| `struct` | structured; not deeply diffed in v1 |

The diff helper canonicalises common aliases — `int64` ↔ `long`,
`float64` ↔ `double`, `decimal(10,2)` → `decimal`,
`timestamp[us]` → `timestamp` — so authors don't need to chase
pyarrow nicknames across surfaces.

## Operating model

- **Configure search paths.**  Set
  `POINTLESSQL_DATA_PRODUCTS_YAML_SEARCH_PATHS` to a list of
  directories or yaml files where data teams ship their
  `pointlessql.yaml`.
- **Load.**  At startup, the data-products page renders the
  cached rows.  Hit `POST /api/data-products/reload` (admin-
  gated) to walk the search paths and UPSERT cache rows.
- **Enforce.**  `pql.write/merge` automatically checks every
  write against the cached contract.  Compliant writes stamp a
  `compliant` event; breaking writes raise and stamp `violated`;
  drift writes (extra columns, type widening) stamp
  `schema_drift_warning` without raising.
- **Alert.**  Set
  `POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS` to a value
  ≥60 to enable the freshness scanner.  A
  `pointlessql.data_product.sla_violated` CloudEvent fires when
  the latest write across the product's tables is older than
  `sla_minutes`; `last_alerted_at` is stamped for re-alert
  suppression (default 60-minute window via
  `re_alert_suppress_minutes`).

## Anti-goals

- **No new UC entity.**  `data_products` is a cache; the source
  of truth is the yaml + git-blame.
- **No DLT-bundle generator.**  PointlesSQL is the platform,
  not an export target.
- **No `Mapped[DataProductRef]` columns.**  `DataProductRef` is
  a `str` subclass; SQLAlchemy reads/writes the underlying
  string transparently.
- **No domain-specific RBAC ladder.**  The existing Workspace +
  scope (admin / supervisor / auditor) surface gates every
  feature in this concept.
- **No Marketplace / Subscription.**  External-consumer
  contracts are out of scope; mailto-Steward is the v1 answer.

## See also

- [`docs/e2e-walkthroughs/data_products.md`](../e2e-walkthroughs/data_products.md)
  — replayable browser + agent + write happy-path.
- [`pointlessql/data_products/`](https://github.com/FloHofstetter/PointlesSQL/tree/main/pointlessql/data_products)
  — the package source.
