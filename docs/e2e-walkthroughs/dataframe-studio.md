# DataFrame Studio — visual query builder → notebook SQL

> **Mode:** `live` · **Surface:** standalone Drawflow editor at `/dataframe-studio`

Replays building a dataframe pipeline visually and handing the compiled
SQL to a notebook. The Studio is the third surface to reuse the shared
Drawflow shell: it supplies the data-product dataframe blocks **minus the
sinks** (no OutputPort / FileOutput / DataProduct) and reuses the
data-product config forms verbatim. It compiles to a governed SELECT
(`canvas_df.compile_to_select`) — no UC materialise, no version ledger.

## Setup

1. Start PointlesSQL + soyuz-catalog (default ports).
2. Seed at least one readable UC table (e.g. via
   `uv run python scripts/seed-e2e.py`) so an Input port has something to
   read. Note its three-part FQN.

## Walkthrough

### Wave 1 — open + compose

1. Navigate to `/dataframe-studio`. The Drawflow stage paints empty with
   a palette on the left listing **Sources** (Input port, File input) and
   **Transforms** (Filter, Project, Join, GroupBy, …). There is **no
   Sinks group** — the Studio never materialises. Console is clean.
2. Drag an **Input port** onto the canvas; in the right drawer set its
   table FQN to the seeded table.
3. Drag a **Filter** onto the canvas and wire the Input port's `out` pin
   to the Filter's `in` pin. The Filter drawer shows a CodeMirror
   predicate editor (reused from the DP editor) with column autocomplete
   from the upstream schema.
4. Set a predicate (e.g. `amount > 0`).

### Wave 2 — compile + preview

1. Click **Compile SQL**. The bottom dock shows the compiled
   `WITH … SELECT * FROM <terminal_cte>` (the terminal is the selected
   node, else the unique leaf). No `LIMIT` is added on compile.
2. Click **Preview**. The top dock runs the slice on DuckDB and shows the
   first rows + a `N rows` count (truncated badge if capped).
3. Validation runs automatically — schema-flow badges colour the edges
   and any type mismatch surfaces in the drawer + the topbar issue badge.

### Wave 3 — guardrails

1. Drag an **Output port** — it is **absent** from the palette. (If a
   saved doc somehow contained one, compile/validate reject it with
   *block 'OutputPort' is not available in DataFrame Studio*.)
2. Point at a node with an unresolved upstream table → compile surfaces
   *table '…' not registered in UC* rather than emitting broken SQL.

### Wave 4 — emit

1. Click **Copy SQL** in the compiled-SQL dock → the governed SELECT is on
   the clipboard.
2. Click **Copy pql.sql(…)** → a ready-to-paste
   `df = pql.sql("""…""")` snippet for a notebook cell.
3. Paste into a notebook `[sql]` (or Python) cell and run it — the SELECT
   executes under the notebook's run-as principal, inheriting
   approved-tables governance (the Studio preview and the notebook run
   share the same compiled SQL).

## Notes

- The Studio reuses `assembleCanvasEditor` + the shared graph bundles +
  the data-product catalog (filtered) + the data-product config-form
  partials; only the catalog filter, the compile/preview/validate routes,
  and the emit actions are Studio-specific.
- Persistence is deliberately client-side (the emitted notebook cell is
  the record of the pipeline); there is no Studio graph table. Re-opening
  a saved Studio graph from a notebook cell is a future iteration.
