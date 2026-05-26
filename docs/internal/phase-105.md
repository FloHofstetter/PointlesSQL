---
title: "Phase 105 — Real-time co-edit (detail)"
audience: contributor
---

# Phase 105 — Real-time co-edit

Closed 2026-05-21.  Sub-sprint detail extracted from `ROADMAP.md` in W2
of the Documentation Master-Plan (per ADR-0009 D7, phases over 100 LOC
move their detail to a per-phase sidecar; the main ROADMAP keeps a
compact summary + pointer).

> See [ROADMAP.md](../../ROADMAP.md) for the project-level context and
> the active/queued roadmap.

## Summary

**Closed 2026-05-21.** Full track shipped in one session: 105.1 (CRDT sidecar storage) + 105.2 (WS hub) + 105.3 (passive Y.Doc client + live pill) + 105.4 (awareness + peer rail) + 105.5 (save-path barrier) + 105.3b (per-cell y-codemirror.next binding) + 105.6 (agent-presence REST + pseudo-peer rendering) + 105.7 (m...

## Full detail

```text
│   └── Phase 105 — Real-time co-edit                              ✅ done 2026-05-21
│         **Closed 2026-05-21.**  Full track shipped in one
│         session: 105.1 (CRDT sidecar storage) + 105.2 (WS hub)
│         + 105.3 (passive Y.Doc client + live pill) + 105.4
│         (awareness + peer rail) + 105.5 (save-path barrier) +
│         105.3b (per-cell y-codemirror.next binding) + 105.6
│         (agent-presence REST + pseudo-peer rendering) + 105.7
│         (multi-tab Playwright playbook) + 105.8 (compaction
│         scheduler executor).
│
│         Original 2026-05-20 framing kept for context:
│         Y.js / CRDT layer over the existing WebSocket so
│         multiple humans + agents can edit cells simultaneously
│         with visible cursors.
│
│         **Decision 2026-05-20:** parked on ice deliberately.  The
│         phase itself was tagged "ship only if the simpler async
│         patterns from Phases 95 / 101 prove insufficient in
│         practice".  Today, the social + AI surfaces shipped in
│         95 (cell-level comments / reactions / followers), 96
│         (inline assistant), 101 (per-cell authorship), and 104
│         (sequence proposals) all use the simpler turn-based async
│         pattern and no user friction with simultaneous-edit
│         scenarios has surfaced yet.
│
│         The infrastructure cost (server-side CRDT backend +
│         Y.js wire format + persistence + conflict resolution
│         that survives the existing reconciliation pass) is
│         substantial and would deflect from the agent-native
│         vision pillars in `project_ai_native_vision.md`.  Revisit
│         only when a concrete user-reported pain story shows the
│         current async pattern is the blocker — until then the
│         per-cell social + provenance surface is the load-bearing
│         collaboration model.
│
│         **Replay bug-hunt 2026-05-20:** a full Playwright-MCP
│         replay of ``docs/e2e-walkthroughs/notebook-editor.md``
│         against the Phase-95 / 96 / 98 surfaces caught five real
│         bugs that escaped every prior gate (no ruff / pyright /
│         pydoclint signal — all five live in JS+Jinja+WS
│         boundaries).  Fixes batched as Phase 105 bug-fix wave;
│         see CHANGELOG ``Unreleased`` for BUG-105-01..05 details.
│         Asset 0.1.0rc44.  Confirms ``feedback_run_playbook_as_gate``
│         — the replay was the gate; nothing earlier would have
│         caught the AI-drawer infinite reconnect, the
│         variable-inspector self-trigger loop, the tag-picker /
│         💬-chip UUID gating, or the ``cellThread.cellRef``
│         snapshot regression.
│
│         **Wave-B follow-up 2026-05-20:** three deferred-UI
│         backends (98.B Tags, 101 Author-Chip, 100 Publish/Share)
│         lifted from "orphan REST + green tests" to "live editor
│         feature" — see Phase 98.B / 100 / 101 entries above for
│         per-phase details.  Replay turned up three more at-source
│         bugs: ``/share/`` missing from auth allowlist (Phase 100
│         viewer unreachable since initial ship), ES-module cache
│         invalidation gap (now structurally fixed via a
│         ``/static/js/{path:path}`` route that stamps ``?v=mtime``
│         into every relative import — mirrors the long-standing
│         ``_style_css`` route for CSS sub-imports), and a tag-
│         payload shape mismatch in the new picker JS.  Asset
│         0.1.0rc46 → rc51 (four sub-bumps across three waves +
│         two bug-bumps).  Tests: 36/36 green across the three
│         touched suites.
│
│         **Wave-D 2026-05-21 — every remaining deferred notebook
│         item closed.**  Six sub-commits + one cross-repo plugin
│         commit asset 0.1.0rc56 → rc62; the per-phase "deferred"
│         lists above flip as follows (full detail in CHANGELOG
│         Unreleased):
│         - Phase 97 — Monaco-diff-style UI (line-by-line unified
│           diff drawer); ``set_revision_signature`` receive
│           endpoint for out-of-band signers.  Pin-to-memory still
│           defers (needs fact-shaped pql.memory primitive).
│         - Phase 98.B — workspace-tree tag-pills + filter
│           dropdown via new ``GET /api/notebooks/tags/bulk``.
│         - Phase 98.C — cell-header lineage chip via
│           ``installCellLineage`` mixin + new bulk endpoint.
│         - Phase 99 — ``pql.widgets`` kernel shim + route-layer
│           ``actor_has_role`` enforcement on load / save /
│           WS-open.
│         - Phase 100 — secret-scrub pass on public viewer +
│           ``GET /embed/notebook_share/{uuid}`` iframe mirror.
│         - Phase 101 — per-cell Review affordance (✅ / ⚠ / 💬
│           decision lattice) on top of the existing polymorphic
│           comment surface (``category='review'`` + migration
│           ``c4e7a91b2f60``).
│         - Phase 102 — ``PQL._branch_remap`` + kernel env-bridge
│           via ``POINTLESSQL_BRANCH``; ``promote_binding`` consults
│           ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL`` so an
│           external reviewer (shoreguard or any other) can gate
│           the transition.
│         - Phase 103 — replay re-execution worker
│           (``services/notebook/replay_worker.py``) drains pending
│           rows via ``jupyter_client.AsyncKernelManager`` per
│           replay.
│         - Phase 104 — hermes-plugin ``pql_propose_cell_sequence``
│           tool fires the ``pql:cell-sequence-proposed`` window
│           event the Wave-C inbox waits for; backend route now
│           accepts ``editor_session_id`` UUID7 for symmetry.
│
│         Genuine blockers (kept deferred):
│         - Shoreguard *sign-revision* and *promote-binding*
│           reviewer APIs do not exist upstream yet; PointlesSQL
│           ships the receive-endpoint + webhook-hook so the
│           integration lands without further PointlesSQL changes
│           once those APIs ship.
│         - Phase 97 pin-to-memory (no fact-shaped pql.memory).
│
│         Phase 105 open follow-ups (out of scope, tracked here so
│         they don't fall off the radar):
│         - **hermes-plugin agent-presence wiring** — ✅ closed
│           2026-05-21.  The notebook chat WS now plumbs
│           ``?notebook_id=`` through to the agent factory, which
│           stamps ``POINTLESSQL_NOTEBOOK_ID`` for the plugin.
│           ``hermes_plugin_pointlessql.tools._common`` ships an
│           ``agent_presence(client, cell_uuid=…)`` context
│           manager that sandwiches every propose / fix / explain
│           tool call with thinking→clear broadcasts to
│           ``POST /api/notebooks/{nb}/coedit/agent-presence``;
│           swallowed-failure semantics so a 5xx on presence never
│           breaks the real tool path.  4 new pytest on the plugin
│           side.  Cross-repo: PointlesSQL ``feat(notebook)`` +
│           plugin ``feat(tools)``.
│         - **Sync-timing rebind on ``cellYBinding``** — ✅ closed
│           2026-05-21.  ``coedit_client.js`` exposes a new
│           ``onSynced`` callback that fires once on
│           ``TAG_SYNC_STEP2``; the mixin in ``coedit.js`` wires
│           ``_rebindCellEditorsAfterSync`` which walks the cell
│           editor registry, destroys every un-bound
│           ``cellEditor``, and re-mounts it with the freshly-
│           available ``yBinding`` triple.  ``cell.source`` is the
│           canonical text the standalone update-listener wrote on
│           every keystroke, so the remount seeds the shared
│           ``Y.Text`` with identical content.  No new pytest
│           (frontend-only; covered by the existing Playwright
│           multi-tab playbook).
│         - **Cell-remap → editor rebind** — 105.5 stashes the
│           remap in ``_pendingCellRemap`` but 105.3b doesn't
│           actively consume it yet.  The first save-after-Pass-3-
│           mint requires a page reload to clean up.  Edge case
│           outside the 105.7 happy path, low priority.
│         - **Multi-worker Uvicorn** — *deliberately* out of scope.
│           The in-process ``_HUBS`` dict makes multi-worker invalid
│           for co-edit; lifting that needs a Redis pub/sub broker
│           and is its own phase, not a 105 follow-up.
│
```
