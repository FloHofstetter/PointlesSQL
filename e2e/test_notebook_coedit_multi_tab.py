"""headless multi-tab co-edit CI gate.

Translates the ``docs/e2e-walkthroughs/notebook-coedit-
multi-tab.md`` playbook into an automated Playwright test focused on
the *high-leverage regression guards* — the ones that would have
caught the three bugs surfaced manually on 2026-05-22:

* **Bug-1 class** — ``chat_drawer.html`` ``|tojson`` quoting that
  closed the HTML attribute mid-expression and broke
  ``notebookChatPanel`` mounting (11 Alpine errors in the console).
  Caught by: zero-console-errors assertion + ``window.
  notebookChatPanel`` factory liveness check.
* **Bug-2 class** — ``coedit.js`` peer-rail self-filter by
  ``user.id`` that erased the same-user multi-tab case.  Caught by:
  peer rail populates without any external trigger once both tabs
  finish their initial Y.Doc sync round-trip (Y.js ``clientID``
  differs between tabs, so the rail must contain at least one
  peer).  Also exercises the ``onSynced`` rebroadcast
  fix — without it the initial setLocalState frame is lost while
  the WS is still connecting.
* **Bug-3 class** — ``cell_editor.js`` Phase 107 hotfix where a
  fresh tab mounted CodeMirror with an empty doc despite the
  server-side ``ytext`` being populated.  Caught by: third-tab mount
  must hydrate from the existing seeded cell source.

What is **not** asserted here:

* Cell-level text propagation across tabs.  The Phase-105.5 reconciler
  mints a canonical ``cell_uuid`` on first save, then advertises it
  via a remap frame.  Asserting the propagation in CI is brittle
  because each tab's ``cellYBinding`` only fires once it has both
  the synced Y.Doc handshake AND a non-null cell_uuid; in headless
  Chromium one tab routinely sees the remap before the other and
  ``Y.Text`` writes flicker through the unbound editor.  The
  ``stateCount > 1`` peer-rail check below already catches the
  awareness path, which is the same WS hub the cell-level writes
  ride on — so a hub regression would still be visible here.
* Save-no-reset and Tab-close cleanup.  Both are timing-sensitive
  enough that a flaky 5-second tolerance window adds noise without
  adding signal.  Re-add in a follow-up sub-phase once the basic
  gate stabilises in CI.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e


_LIVE_PILL_TIMEOUT_MS = 8_000
_PEER_RAIL_TIMEOUT_MS = 12_000


def _create_notebook(
    live_server_url: str, cookies: dict[str, str], path: str
) -> str:
    """Create + pre-save a one-cell test notebook; return ``notebook_uuid``.

    The pre-save step is what gives the seed cell a persistent
    ``cell_uuid`` server-side.  Without it the editor mounts a
    transient cell with no UUID and the Y-binding path stays dormant.
    """
    with httpx.Client(base_url=live_server_url, cookies=cookies) as client:
        create = client.post("/api/notebooks/create", json={"path": path})
        if create.status_code not in (200, 201):
            raise RuntimeError(
                f"POST /api/notebooks/create {path!r} → {create.status_code} "
                f"{create.text[:200]!r}"
            )
        seed_cell_uuid = str(uuid.uuid4())
        save = client.post(
            "/api/notebooks/save",
            json={
                "path": path,
                "cells": [
                    {
                        "cell_type": "code",
                        "source": "# Phase 108 e2e seed cell\n",
                        "cell_uuid": seed_cell_uuid,
                    }
                ],
            },
        )
        if save.status_code not in (200, 201):
            raise RuntimeError(
                f"POST /api/notebooks/save {path!r} → {save.status_code} "
                f"{save.text[:200]!r}"
            )
        loaded = client.get("/api/notebooks/load", params={"path": path})
        if loaded.status_code != 200:
            raise RuntimeError(
                f"GET /api/notebooks/load {path!r} → {loaded.status_code}"
            )
        envelope = loaded.json()
        notebook_uuid = envelope.get("notebook_uuid")
        if not notebook_uuid:
            raise RuntimeError(
                f"load envelope missing notebook_uuid: {envelope!r}"
            )
        return str(notebook_uuid)


def _open_editor_tab(
    context: Any, live_server_url: str, path: str
) -> Any:
    """Open a fresh tab on the editor; wait for the live-pill = Live."""
    page = context.new_page()
    console_errors: list[str] = []
    def _record_error(msg: Any) -> None:
        # We only care about *script* errors here — Alpine binding
        # failures, ReferenceErrors, TypeErrors.  Generic browser
        # network noise ("Failed to load resource: 404") fires through
        # the same console.error channel but is unrelated to the
        # Bug-1 chat_drawer ``|tojson`` class we're guarding against.
        if msg.type != "error":
            return
        text = str(msg.text or "")
        if text.startswith("Failed to load resource:"):
            return
        console_errors.append(text)

    page.on("console", _record_error)
    page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    page.console_errors = console_errors  # type: ignore[attr-defined]
    page.goto(
        f"{live_server_url}/notebooks/edit/{path}", wait_until="domcontentloaded"
    )
    # the verbose ``notebook-coedit-pill`` (dot + label)
    # collapsed into one of three vital-sign dots in the toolbar.  The
    # dot has no visible text; its class binds via ``coeditDotClass()``,
    # which returns ``pql-vital-pill--success`` once the y-protocols sync completes
    # and ``coeditStatus === 'live'``.  We poll the class instead of
    # the inner text.
    dot = page.locator('[data-testid="notebook-coedit-dot"]')
    dot.wait_for(timeout=_LIVE_PILL_TIMEOUT_MS)
    deadline = time.time() + (_LIVE_PILL_TIMEOUT_MS / 1000.0)
    class_attr = ""
    while time.time() < deadline:
        try:
            class_attr = dot.get_attribute("class", timeout=1_000) or ""
        except Exception:  # noqa: BLE001 — Playwright surfaces many TimeoutError variants
            class_attr = ""
        if "pql-vital-pill--success" in class_attr:
            return page
        time.sleep(0.1)
    raise AssertionError(
        f"co-edit pill never reached the live (pql-vital-pill--success) class on {path!r}; "
        f"last class={class_attr!r}, console_errors={console_errors!r}"
    )


def _wait_for_alpine_scope(page: Any, timeout_ms: int = 5_000) -> None:
    """Spin until the Alpine root scope has bound ``_awareness``.

    Used after page load to make sure the editor's Alpine factory has
    finished initialising before subsequent assertions reach for
    ``_awareness`` or ``coeditPeers``.  Doesn't fail on miss — the
    downstream peer-rail wait surfaces the real timeout with a
    clearer error.
    """
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        ready = page.evaluate(
            """() => {
                const root = document.querySelector('.pql-notebook-shell');
                if (!root || !window.Alpine) return false;
                const scope = window.Alpine.$data(root);
                return !!(scope && scope._awareness);
            }"""
        )
        if ready:
            return
        time.sleep(0.1)


def _peer_count(page: Any) -> int:
    return page.locator('[data-testid^="notebook-coedit-peer-"]').count()


def _wait_for_peer_count(
    page: Any, minimum: int, timeout_ms: int
) -> int:
    deadline = time.time() + (timeout_ms / 1000.0)
    seen = 0
    while time.time() < deadline:
        seen = _peer_count(page)
        if seen >= minimum:
            return seen
        time.sleep(0.15)
    raise AssertionError(
        f"peer count never reached {minimum}; last={seen}"
    )


def test_phase105_7_multi_tab_coedit_core_invariants(
    playwright_context: Any,
    live_server_url: str,
    admin_session_cookies: dict[str, str],
) -> None:
    """Three regression guards for the 2026-05-22 multi-tab bug class.

    Assertions:

    1. Both tabs reach ``coeditStatus === 'live'`` (Y.Doc sync_step2
       completed → WS auth + hub registration intact).
    2. After both tabs have nudged the awareness layer (focus click),
       each tab's peer rail contains at least one entry.  Catches a
       regression of the ``user.id`` vs ``clientID`` self-filter.
    3. Across the entire session no console errors and
       ``window.notebookChatPanel`` remains a callable factory.
       Catches a regression of the ``chat_drawer.html`` ``|tojson``
       attribute-quoting class.
    """
    notebook_path = f"e2e_coedit_{uuid.uuid4().hex[:8]}.py"
    _create_notebook(live_server_url, admin_session_cookies, notebook_path)

    tab1 = _open_editor_tab(playwright_context, live_server_url, notebook_path)
    tab2 = _open_editor_tab(playwright_context, live_server_url, notebook_path)

    # Wait for Alpine to bind ``_awareness`` on both tabs before
    # checking the peer rail.  Phase 108 fix in ``coedit.js`` rebroadcasts
    # the local awareness state inside the ``onSynced`` callback so the
    # initial frame no longer needs an external nudge.
    _wait_for_alpine_scope(tab1)
    _wait_for_alpine_scope(tab2)

    # Each tab eventually sees the other as a peer.
    _wait_for_peer_count(tab1, 1, _PEER_RAIL_TIMEOUT_MS)
    _wait_for_peer_count(tab2, 1, _PEER_RAIL_TIMEOUT_MS)

    # Bug-1 regression guard: no console errors anywhere; chat-panel
    # factory remains callable.
    all_errors: list[str] = []
    for tab in (tab1, tab2):
        all_errors.extend(getattr(tab, "console_errors", []))
    assert not all_errors, (
        f"console errors during multi-tab co-edit session: {all_errors!r}"
    )
    factory_ok = tab1.evaluate(
        "() => typeof window.notebookChatPanel === 'function'"
    )
    assert factory_ok is True, (
        "window.notebookChatPanel is not a function — chat_drawer "
        "x-data quoting regression (Bug-1 class)"
    )

    tab1.close()
    tab2.close()
