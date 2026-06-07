---
title: "Phase 198 — E2E-in-CI Vollabdeckung (alle Playbooks automatisiert) (plan)"
audience: contributor
---

# Phase 198 — E2E-in-CI Vollabdeckung

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206).
Direkte Fortsetzung von Phase 190 (E2E-CI-Automatisierung Tier-1/2): 190
automatisiert ~14 Top-Journeys, **diese Phase treibt auf 100 %** der
deterministischen Playbooks und etabliert die Coverage-Ledger-Ratsche.

## Warum

Heute hängen **188 Phasen UI hinter genau 3 e2e-Testfunktionen**
([`e2e/test_smoke.py`](../../e2e/test_smoke.py) = 2,
[`e2e/test_notebook_coedit_multi_tab.py`](../../e2e/test_notebook_coedit_multi_tab.py)
= 1), während **92 deterministische Playbooks**
([`docs/e2e-walkthroughs/`](../../docs/e2e-walkthroughs/)) nur *manuell*
replaybar sind. Jeder Browser-Replay ist Handarbeit; jede UI-Regression
zwischen den Replays ist unsichtbar bis zum nächsten manuellen Durchlauf.

Phase 190 schließt die Lücke für die wichtigsten ~14 Journeys. Diese Phase
macht den Rest planbar abarbeitbar — ein Playbook pro Einheit, ideal für
autonomes Vorankommen — und verhindert per **Coverage-Ledger**, dass neue
UI-Surfaces ohne automatisierten Replay landen.

## Ausgangslage (Fakten)

- **92 Playbooks**, 4 Modi (README-Tabelle
  [`docs/e2e-walkthroughs/README.md:29-146`](../../docs/e2e-walkthroughs/README.md)):
  browser (50), hybrid notebook/CLI+browser (14), hermes agent-only (7),
  curl JSON-API (2).
- **e2e-Infrastruktur** ([`e2e/conftest.py`](../../e2e/conftest.py)):
  `live_server_url` (uvicorn + tempfile-SQLite + geseedeter Admin),
  `admin_session_cookies` (CSRF+Form-Login), `playwright_browser`
  (headless Chromium), `playwright_context` (frische BrowserContext je
  Test). **Kein Page-Object-Muster**, direkte Playwright-API.
- **CI** ([`.github/workflows/test.yml:125-152`](../../.github/workflows/test.yml)):
  Job `e2e-browser` läuft `pytest -q e2e/ -m e2e`, **`continue-on-error:
  true`** (nicht-blockierend), installiert Chromium `--with-deps`. **Kein
  soyuz-catalog-Sidecar** in CI → Katalog-/Lineage-/Federation-Journeys
  heute nicht ausführbar.
- **Marker** ([`pyproject.toml:116-131`](../../pyproject.toml)): `e2e`,
  `integration`, `postgres`; `testpaths=["tests"]` (e2e/ nicht
  default-collected); addopts schließt `e2e`+`integration` aus.
- **Seeds**: [`scripts/seed-e2e.py`](../../scripts/seed-e2e.py) (idempotent),
  `seed-full-stack-demo.py` (grand-tour), `pg-seed.sql` (Foreign-Catalog).
- **Env-Overlays** ([`docker/docker-compose.e2e.yml:29-50`](../../docker/docker-compose.e2e.yml)):
  scheduler-tick, JUPYTER_ENABLED, LOG_FORMAT, OIDC-Trio + mock-oidc-
  Sidecar, postgres-e2e-Sidecar.

## Scope (Wellen)

### W1 — soyuz-catalog als CI-Service + `requires_soyuz`-Marker
- Phase-190-Entscheidung umsetzen: soyuz-catalog im e2e-Job als
  Service/Container booten (gepinnter Tag, wie Docker-Flow), Health-Gate
  vor Testlauf. Neuer Marker `requires_soyuz` trennt katalog-abhängige von
  reinen-UI-Playbooks, damit Letztere ohne Server laufen.
- Damit werden die Katalog-/Lineage-/Federation-/DP-Playbooks überhaupt
  erst automatisierbar.

### W2 — Page-Object-Layer + Journey-Registry (auf 190 aufbauend)
- `e2e/pages/` (Page-Objects pro Surface; aus 190 übernehmen/erweitern)
  statt copy-paste-Selektoren. `e2e/_journeys.py`: Registry Test →
  Quell-Playbook (Rückverfolgbarkeit: jeder Test nennt sein `.md`).
- `e2e/seed/`-Fixtures pro Surface-Gruppe; Playbook-Abhängigkeitskette
  (auth → catalog → … ) als Fixture-Reihenfolge oder per-Test-DB-State.

### W3 — Browser-Playbooks automatisieren (50, gruppenweise)
- Eine Welle je Surface-Gruppe (≈8–10 Playbooks): catalog/inline-editors,
  audit-cockpit/forensics, branches/rollback, dp-canvas/mesh-canvas,
  ml-registry, dbt, admin-console, lens/sql-editor, notebook-editor,
  governance/policy. Jedes Playbook → eine pytest-Funktion, die die
  Markdown-Schritte in Playwright-Aktionen abbildet (Schritt-Mapping aus
  dem Playbook-Format).
- Pro Welle den Coverage-Ledger fortschreiben.

### W4 — Hybrid- + curl-Playbooks (16)
- Hybrid (14): Notebook/CLI-Prelude vor Browser-Schritten — Prelude als
  Fixture (papermill/CLI-Aufruf im e2e-Job), dann Browser-Assertions.
  Subprozess-schwere Journeys (Jupyter/MLflow/dbt) per Marker steuerbar
  halten (Phase-190-Non-Scope respektieren oder gezielt einschalten).
- curl (2): reine httpx-API-Tests (`git-backed-workspaces`,
  `external-sql-api`) — schnell, kein Browser.

### W5 — Hermes-Playbooks (7) + Visual-Regression-Baseline
- Hermes-agent-only-Journeys über die Agent-Run-/MCP-Surface
  (programmatisch, kein Browser) — soweit ohne Live-LLM deterministisch
  machbar; sonst als dokumentierte Lücke im Ledger.
- Optionale Visual-Regression-Baseline (Screenshot-Diff auf Schlüssel-
  seiten, großzügige Toleranz) als nicht-blockierender Nightly-Zusatz.

### W6 — Gate scharf schalten + Flake-Kontrollen
- `continue-on-error` entfernen, sobald die Suite stabil grün läuft
  (Muster wie der ursprüngliche e2e-Job: ~10 grüne Runs vor Gate).
- Flake-Kontrollen: rerun×1 bei Fehlschlag, Screenshot-on-fail-Artifact,
  feste Viewports/Waits (kein `sleep`, nur `wait_for`).
- Coverage-Ledger-Gate: neuer HTML-Route ohne Ledger-Eintrag failt.

## Akzeptanzkriterien
- Coverage-Ledger zeigt jedes der 92 Playbooks als „automatisiert" oder
  „bewusst ausgenommen mit Grund" — keine stillen Lücken.
- soyuz-catalog bootet im CI-Job; katalog-abhängige Journeys laufen grün.
- Der e2e-Job ist **blockierend** (kein `continue-on-error`) und stabil.
- Ein bewusst eingebauter UI-Regress (z. B. fehlender Submit-Button)
  lässt den passenden Journey-Test fehlschlagen.
- Lokal: `uv run pytest e2e/ -m e2e` reproduziert die CI-Auswahl.

## Risiken / Notizen
- **Flake** ist das Hauptrisiko bei 90+ Browser-Tests; strikt
  `wait_for`-basiert, deterministische Seeds, feste Viewports.
- Firefox-vs-Chromium: CI nutzt gebündeltes Chromium; die MCP-manuelle-
  Replay-Doku nutzt Firefox (siehe CLAUDE.md / Sprint-22 `3f1da76`) —
  Selektoren browserneutral halten.
- CI-Laufzeit wächst spürbar; ggf. nach Surface-Gruppe sharden
  (pytest-xdist / Matrix-Jobs).
- Verwandt: Phase 7 (erste Playwright-Walkthroughs), Phase 69 (Vollreplay),
  Phase 190 (Tier-1/2), [[playwright-firefox-node24-extractor-hang]].
