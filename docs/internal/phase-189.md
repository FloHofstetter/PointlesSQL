---
title: "Phase 189 — Mutation-Testing-Gate (mutmut committen + CI-Ratsche) (plan)"
audience: contributor
---

# Phase 189 — Mutation-Testing-Gate

**Status: 🔜 next (geplant 2026-06-05).** Detail-Sidecar für den
ROADMAP-Eintrag; siehe [ROADMAP.md](../../ROADMAP.md) für den
Cluster-Kontext (Quality-Consolidation 189–191).

## Warum

Die Quality-Welle vom 1.–5. Juni 2026 hat ~880 Mutation-Survivors
gekillt und gezielt **Pure-Seams** aus den Orchestratoren extrahiert,
damit deren Entscheidungslogik unit-testbar wird (Commits
`1c2e7d1e` papermill-executor, `3acb1bdb` replay-worker, `567f00b6`
alert-check, `533f51ce` run-execution, `e04132d5` ingest-pull,
`af48e3df` chat-loop, `eb4c83e8` Integration-Shells).

**Das Problem:** Es gibt *keine committete mutmut-Config und kein
CI-Gate.* Das Setup lebt nur in einer Session-Memory. Damit ist die
gesamte Investition ungeschützt — der nächste Feature-Commit kann
Survivors lautlos wieder einschleppen, und niemand merkt es. Diese
Phase macht aus dem Einmal-Aufwand eine **permanente Ratsche**:
Harness committen, Baseline einfrieren, Regression in CI verhindern.

## Ausgangslage (Fakten)

- Kein `setup.cfg`; `pyproject.toml` hat keinen `[tool.mutmut]`-Block
  (bewusst — mutmut liest dann `setup.cfg`).
- mutmut 3.5 läuft auf Python 3.14 via `uv run --with mutmut`.
- ~53k Mutanten über `pql/` + `services/`; voller Lauf ~2 h auf
  12 Kernen. Nicht abgedeckte Mutanten → exit 33 sofort (gratis), nur
  abgedeckte kosten Zeit.
- Vier reale Setup-Blocker (alle in der Memory dokumentiert):
  1. Trampoline liest `os.environ['MUTANT_UNDER_TEST']` mit hartem
     Index → KeyError, wenn ein Test `os.environ` ganz austauscht. Fix:
     Wrapper patcht `mutmut.trampoline_templates.trampoline_impl` auf
     `.get(...,'')` **vor** dem Import von `mutmut.file_mutation`.
  2. Quell-scannende Meta-Tests müssen raus
     (`--ignore=tests/test_no_bare_http_exception.py`,
     `--ignore=tests/test_no_lossy_broad_except.py`); `__doc__`-
     introspizierende Tests `--deselect` (Trampoline droppt Docstrings).
  3. mutmut läuft pytest mehrfach im selben Prozess → Tests, die
     Modul-Globals ohne Cleanup mutieren, fallen im 2. Lauf um (der
     citation-registry-Leak wurde auf main schon gefixt, `c9dac3ac`).
  4. cwd ist `mutants/`; alles, was per Relativpfad geladen wird
     (z. B. `frontend/templates` via `Path(__file__).parents[2]`),
     muss in `also_copy`.
- Restliche Survivors leben in tiefen async-Orchestratoren
  (`pull_mapping`, `run_chat_turn`, `_alert_check_executor`,
  `scheduler/runs/*`, `replay_worker`, `papermill`) — Integration-
  Territorium — plus echte **äquivalente Mutanten** (`typing.cast`-
  No-ops, kosmetische Fehler-Strings, Timing-Arithmetik).

## Scope (Wellen)

### W1 — Harness committen (Config + Wrapper, noch kein Gate)
- Neues `setup.cfg` mit `[mutmut]`-Section:
  - `paths_to_mutate = pointlessql/pql/, pointlessql/services/`
  - `also_copy = pointlessql/, frontend/, alembic.ini`
  - `pytest_add_cli_args = --ignore=tests/test_no_bare_http_exception.py
    --ignore=tests/test_no_lossy_broad_except.py
    --deselect=tests/test_pql_introspect_routes.py::<die zwei doc-Tests>`
  - `pyproject.toml` bleibt sauber (kein `[tool.mutmut]`).
- Neues `scripts/mutation/run_mutmut.py`: kapselt den Trampoline-
  Monkeypatch (vor `mutmut.file_mutation`-Import) und ruft mutmut auf.
  Ein Befehl für Contributors statt vier manuelle Workarounds.
  Optionaler `--only <glob>` für die scoped-Re-verify-Schleife.
- Neues `scripts/mutation/README.md`: voller Lauf, scoped-Schleife
  (`rm mutants/mutmut-stats.json` + Glob), Lesen von
  `mutants/<path>.py.meta` (`exit_code_by_key`: 0=survived,
  1/3=killed, 33=no-test, 36/255=timeout).
- `.gitignore`: `mutants/`, `mutmut-stats.json`.
- **Check:** verifizieren, dass heute kein Tool `setup.cfg` liest
  (ruff/pytest/pyright-Config alle in pyproject) — sonst kollidiert
  die neue Datei nicht.

### W2 — Baseline + Äquivalent-Allowlist
- Voller Lauf; Per-Modul-Survivor-Zahlen als committete Baseline
  (`scripts/mutation/baseline.json`: Modul → {killed, survived,
  no_test, equivalent}).
- Kuratierte Äquivalent-Allowlist (`scripts/mutation/equivalent.txt`):
  Mutant-Keys, die nachweislich äquivalent sind, je eine
  Begründungszeile — analog zum `ALLOWLIST`-Pattern in
  [check-file-size-budget.sh](../../scripts/check-file-size-budget.sh).
  Das ist die „bekannt-akzeptierte Survivors"-Menge, damit das Gate
  sie nicht flaggt.

### W3 — CI-Gate (PR-inkrementell + Nightly-Full)
- **PR-Gate** (`scripts/check-mutation-budget.sh` + CI-Step): geänderte
  `pointlessql/{pql,services}/**.py` aus dem PR-Diff bestimmen, mutmut
  scoped nur auf diese Module (frische Stats ~3 min + nur deren
  Mutanten, ~4–5 min/Modul), und **fehlschlagen, sobald ein *neuer*
  Survivor auftaucht, der nicht in der Äquivalent-Allowlist steht.**
  Hält die PR-Latenz beschränkt (nur geänderte Module), verhindert
  aber Regression genau dort, wo sie eingeführt wird.
  - Rename/Split-Handling: ein Split verschiebt Code → alten **und**
    neuen Pfad behandeln.
- **Nightly** (`.github/workflows/mutation-nightly.yml`): voller
  pql+services-Lauf (~2 h), Survivor-Diff als Artifact hochladen,
  optional ein Tracking-Issue mit neu-überlebten Mutanten
  refreshen. **Nicht-blockierend** — informative Ratsche. Bei Wachstum
  nach Paket sharden (pql vs services als zwei Jobs).
- **Kein** pre-commit-Hook (zu langsam) — Gate bleibt CI-only.

### W4 — Restliche killbare Hotspots schließen
- Die Memory-Frontier abarbeiten: jeden verbleibenden Orchestrator-
  Entscheidungskern in ein **pures Sibling-Modul** extrahieren (das
  bewiesene Muster aus `af48e3df`/`3acb1bdb`/…) und unit-testen; die
  dünne async-Hülle integration-covern (Muster `eb4c83e8`).
- Ziel: **jeder nicht-äquivalente Survivor ist entweder gekillt oder
  bewusst allowlisted.**

## Akzeptanzkriterien
- `bash scripts/check-mutation-budget.sh` grün auf sauberem main.
- Ein absichtlich eingebauter Survivor in einem geänderten Modul
  lässt das PR-Gate fehlschlagen.
- Nightly-Workflow läuft grün und lädt das Survivor-Artifact hoch.
- `setup.cfg` + `scripts/mutation/` committet;
  `uv run python scripts/mutation/run_mutmut.py` funktioniert auf
  frischem Checkout.
- `pyproject.toml` bleibt frei von `[tool.mutmut]`.

## Risiken / Notizen
- `also_copy`-Vollständigkeit ist die häufigste Stolperfalle (Relativ-
  pfad-Assets unter `mutants/`). Bekannt, in W1 abgedeckt.
- Neue Modul-Global-Leaks tauchen als 2.-Lauf-Fehler auf → die scoped
  Gate-Läufe fangen sie; an der Quelle fixen (nie maskieren).
- ~2 h Nightly ist ok; bei Wachstum sharden.
- Verwandte Memory: `mutmut-harness-setup` (vollständige Setup-Doku +
  Gotchas).
