---
title: "Phase 190 — E2E-CI-Automatisierung (Top-Journeys aus den Playbooks) (plan)"
audience: contributor
---

# Phase 190 — E2E-CI-Automatisierung

**Status: 🔜 next (geplant 2026-06-05).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Cluster Quality-Consolidation 189–191).

## Warum

Das auffälligste Risiko/Leverage-Missverhältnis im Projekt: **188
Phasen UI hinter genau 2 automatisierten Playwright-Tests**
([e2e/test_smoke.py](../../e2e/test_smoke.py) +
`test_notebook_coedit_multi_tab.py`). Gleichzeitig liegen **92
deterministische Markdown-Playbooks** in
[docs/e2e-walkthroughs/](../../docs/e2e-walkthroughs/), die jeden
Journey mit expliziten Asserts + MCP-Skript spezifizieren — aber nur
manuell/per-Claude replaybar sind.

Die Top-kritischen Journeys als automatisierte pytest-Playwright-Tests
zu codieren schützt die **gesamte** Oberfläche gegen Regression. Bei
einer Codebasis, die weiter wächst, ist das der Unterschied zwischen
mutigem Refactoring und Angst vor jedem Commit. Das ist die natürliche
Fortsetzung des Quality-Fokus: von „ist der Code isoliert korrekt"
(Mutation, Phase 189) zu „funktioniert das Produkt end-to-end".

## Ausgangslage (Fakten)

- [e2e/conftest.py](../../e2e/conftest.py) hat einen vollständigen
  Fixture-Stack: `live_server_url` (echte Prod-Lifespan-uvicorn auf
  Tempfile-SQLite, alembic upgrade head, admin-Seed),
  `admin_session_cookies` (CSRF + form-encoded `/auth/login`),
  `playwright_browser` (headless Chromium), `playwright_context`
  (function-scope, Auth-Cookies vorinjiziert).
- CI-Job heute: `uv run pytest -q e2e/ -m e2e` mit
  `playwright install chromium`.
- Walkthroughs sind MCP-Skript-Playbooks
  (`browser_navigate`/`click`/`evaluate` + Asserts) — nahezu 1:1 in die
  Playwright-Sync-API übersetzbar (`page.goto`/`click`/`evaluate`).
- **Constraint 1 — Subprozesse aus:** Die e2e-Fixture deaktiviert
  Jupyter/MLflow/dbt/Scheduler bewusst für schnellen Boot. Journeys,
  die davon abhängen (open-in-notebook → :8888, MLflow-Proxy, dbt-Docs),
  laufen so nicht im headless-Job → out of scope oder per-Test-Opt-in.
- **Constraint 2 — Seed + soyuz:** Die Walkthroughs setzen
  [scripts/seed-e2e.py](../../scripts/seed-e2e.py) voraus (Katalog
  `demo` + Schemas `sales`/`hr` + 4 Tabellen). Die e2e-conftest seedet
  heute **nur** einen Admin-User, **nicht** den Demo-Katalog. Und der
  Katalog lebt in **soyuz-catalog** (separater Prozess), den der
  e2e-Job heute nicht bootet.

## ⚠️ Zentrale Architektur-Entscheidung (vor W2 zu treffen)

Die Katalog-/Lineage-/Tabellen-Journeys brauchen ein befülltes UC,
also einen laufenden soyuz-catalog. Zwei Optionen:

- **(a) [empfohlen] soyuz-catalog als CI-Service booten** — `uv run
  soyuz-catalog` gegen ein Tempdir (oder als docker-Service), gepinnt
  auf denselben Tag wie `[tool.uv.sources]`, mit Health-Probe vor dem
  Seed. Macht die wertvollen Katalog-/Lineage-/Tabellen-Journeys
  erreichbar. Hinter einem `requires_soyuz`-Marker, damit der Job
  lokal ohne soyuz **degradiert** statt zu failen.
- **(b) Journeys auf PointlesSQL-only-Surfaces beschränken**, die kein
  befülltes UC brauchen — deutlich kleinere Abdeckung.

→ Plan geht von **(a)** aus. Diese Entscheidung ist der einzige echte
neue bewegliche Teil; falls (b) gewünscht ist, schrumpft W2/W3
entsprechend.

## Scope (Wellen)

### W1 — Seed + Helper-Fundament
- `seeded_demo`-Fixture (session-scope): ruft
  [scripts/seed-e2e.py](../../scripts/seed-e2e.py) (bzw. dessen
  importierbaren Kern) gegen die Live-Server-DB + soyuz. Hängt an der
  Architektur-Entscheidung oben.
- Neues `e2e/pages/`-Helfermodul (leichtgewichtige Page-Objects): ein
  Helper je Surface (`CatalogPage`, `SqlEditorPage`, `NotebookPage`,
  `AuditPage`, `DpCanvasPage`, `BranchPage`), der die repetitiven
  navigate+assert-Idiome kapselt — spiegelt die Walkthrough-Struktur,
  sodass ein Playbook auf eine Helper-Methoden-Sequenz mappt.
- `e2e/_journeys.py`-Registry: mappt jeden Test auf sein Quell-Playbook
  (`docs/e2e-walkthroughs/NAME.md`) für Nachvollziehbarkeit.

### W2 — Tier-1 kritische Journeys (must-not-break, ~8 Tests)
Höchster Breakage-Impact, ohne deaktivierte Subprozesse:
1. **catalog-browsing** (Katalog→Schema→Tabelle, PQL-Snippet,
   Sidebar-Persistenz) — `catalog-browsing.md`
2. **sql-editor** (SELECT absenden, Ergebnisse, History) —
   `sql-editor.md`
3. **sql-editor-writes** (AST-dispatch-Write-Pfad) —
   `sql-editor-writes.md`
4. **audit-cockpit** (Inbox, Badge, FTS) — `audit-cockpit-deep.md`
5. **branches** (create/preview/promote/discard) — `branches.md`
6. **rollback** (Run → Rollback) — `rollback.md`
7. **dp-canvas-builder** (Canvas öffnen, Block, Wire, Materialize) —
   `dp-canvas-builder.md`
8. **data-products** (browse/detail) — `data-products.md`

Jeder: Playbook-Asserts → Playwright-pytest, `@pytest.mark.e2e`, via
Page-Helper. **`networkidle` meiden** (Smoke-Test dokumentiert die
Live-WS-Falle) — `domcontentloaded` + explizites
`wait_for(text=…)`.

### W3 — Tier-2 + Negativ-/Auth-Pfade (~6 Tests)
- Lineage Row/Column/Value-Trace — `inference-lineage.md`
- Federation-Read — `federation.md`
- Governance/Policy — `computational-policy-as-code.md`
- **Non-admin-403-Negative** (die Auth-Gating-Asserts aus
  `catalog-browsing.md` Schritt 9) via zweitem geseedeten non-admin
  User + `viewer_context`-Fixture.
- **Error-Envelope-Form** (`error-handling.md`) — `{"error":{"code":…}}`
  bei erzwungenem 403/404 asserten.

### W4 — CI-Verdrahtung als Ratsche + Flake-Kontrollen
- e2e-Job läuft schon `pytest e2e/ -m e2e` → neue Tests werden
  automatisch erfasst. soyuz-Service-Step ergänzen (W1-Entscheidung).
- **Flake-Kontrollen:** kleiner Retry (`pytest-rerunfailures`,
  `--reruns 1` scoped auf e2e-Marker) für timing-sensitive Browser-
  Schritte; Per-Test-Timeout; **Screenshot-on-failure** als Artifact
  (`page.screenshot` im Teardown bei Fehler).
- **Coverage-Ledger** (`scripts/check-e2e-coverage.sh`, optional):
  diffed `e2e/_journeys.py` gegen `docs/e2e-walkthroughs/*.md` und
  loggt, welche Playbooks **noch nicht** automatisiert sind — ein
  sichtbares „no silent caps"-Protokoll, kein Hard-Gate.

## Akzeptanzkriterien
- `uv run pytest e2e/ -m e2e` läuft Tier-1+2 grün, lokal (mit soyuz)
  und in CI.
- Jeder Test nennt sein Quell-Playbook.
- Eine absichtlich kaputte Route (z. B. Button entfernen) lässt den
  zugehörigen Journey-Test fehlschlagen.
- Screenshot-Artifacts werden bei Fehler hochgeladen.

## Non-Scope (bewusst aufgeschoben — im Ledger protokolliert)
- Journeys, die JupyterLab (open-in-notebook → :8888), MLflow-Proxy
  oder dbt-Docs brauchen — erfordern die deaktivierten Subprozesse;
  später per Per-Test-Opt-in.
- Visual-Regression / Screenshot-Diffing — nur assertion-basiert.
- Voll-Parität über alle 92 Playbooks — Ziel ist Tier-1+2 (~14); der
  Rest bleibt manueller Replay, im Ledger getrackt.

## Risiken
- soyuz-catalog als CI-Service ist der Hauptneubau — selber Tag wie
  pyproject, Health-Probe vor Seed.
- Browser-Flakiness — gemindert durch kein-networkidle, explizite
  Waits, beschränkte Reruns.
- Seed-Determinismus — Walkthroughs setzen deterministische Seeds
  voraus; `scripts/seed-e2e.py` unverändert wiederverwenden.

## Verwandte Memory
- `playwright-firefox-node24-extractor-hang` (Browser-Install-
  Workaround auf dieser Maschine; CI nutzt Chromium, lokal Firefox).
