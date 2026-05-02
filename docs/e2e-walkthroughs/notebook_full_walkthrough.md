# Notebook full walkthrough — 

Deterministic click-through of every output-rendering + editing
surface in the native Python notebook editor. Pairs with the
 (UUID-free marker grammar) and (manual-edit
tolerance) refactors — any future sprint that touches
``notebook_editor.html``, ``frontend/js/notebook/*.js``,
``services/notebook_doc.py``, ``services/kernel_session/*`` or the
``notebook_outputs`` DB layer MUST replay this playbook before
landing. Fixes for surfaced bugs either inline (trivial) or as
``BUG-98-NN`` follow-up tags at the bottom.

## Preconditions

- [`auth.md`](auth.md) ran first — admin session cookie is live.
- soyuz-catalog is running at ``http://127.0.0.1:8080`` (launch with
 ``uv run uvicorn soyuz_catalog.api.main:create_app --factory
 --host 127.0.0.1 --port 8080`` inside ``~/git/soyuz-catalog``).
- PointlesSQL is running at ``http://127.0.0.1:8000`` (launch with
 ``uv run pointlessql`` inside the PointlesSQL checkout).
- A writable notebooks dir — default
 ``${POINTLESSQL_JUPYTER_NOTEBOOKS_DIR:-./notebooks}``.

Open Firefox (Playwright-MCP: pass ``--browser firefox``; the
bundled chrome-for-testing works too). Screenshots land under
``docs/e2e-walkthroughs/screenshots/sprint-98/``.

## Walkthrough

1. **Open a fresh notebook** — navigate to
 ``/notebook/editor?path=sprint98_walkthrough.py``. The editor
 opens with a single empty cell whose marker is exactly ``# %%``
 — **no** ``pql_cell_id="…"`` segment ( invariant).
 - Assert: the toolbar shows "Kernel ready", "Pyright ready",
 "Saved". Screenshot:
 ``01-initial-open-fresh-notebook.png``.

2. **D.01 — stdout (``print``)** — set the cell source to
 ``print("hello world")`` (via
 ``window.monaco.editor.getEditors()[0].getModel().setValue("# %%\nprint(\"hello world\")\n")``)
 and click Run cell.
 - Assert: a fresh output zone appears under the cell with the
 text ``hello world``. The status pill flips to ``ok`` in
 < 1 s and an execution-count badge is set. Screenshot:
 ``02-print-hello-world.png``.

3. **D.02 — pandas DataFrame** — set the source to
 ``import pandas as pd\npd.DataFrame({"a": [1,2,3], "b":
 ["x","y","z"]})`` and Run cell.
 - Assert: an HTML table renders in the output zone with column
 headers ``a`` / ``b`` and three rows. Bordered cells, fixed
 column widths. Screenshot: ``03-pandas-dataframe.png``.

4. **D.03 — matplotlib plot** — set the source to a minimal
 ``plt.subplots`` + ``ax.plot`` + ``fig`` snippet and Run cell.
 - **Conditional:** if matplotlib is not installed in the
 kernel's Python env, the traceback is shown instead (still a
 valid rendering test — the ``error`` mime bundle path paints
 red-coloured frames). Screenshot:
 ``04-matplotlib-plot.png``.
 - When matplotlib IS installed: a PNG image appears scaled to
 the cell width.

5. **D.04 — markdown cell** — set the source to a
 ``# %% [markdown]`` cell with ``##`` heading, bold, italic,
 list, and link lines.
 - Assert: the marker renders as ``# %% [markdown]`` (no UUID).
 A view-zone preview **should** appear rendering the markdown
 — any source line between the marker and the next ``# %%``
 is hidden from the Monaco view (earlier behaviour).
 Screenshot: ``05-markdown-cell.png``.
 - **Known limitation** (tracked as BUG-98-01 — superseded
 by the dirty-flag + zone-prune work,
 but the preview's initial paint after a ``setValue``
 still needs a manual click to materialise. Low priority
 — a real user adds the cell via the ``+ Markdown``
 button, which triggers ``rebuildMarkdownZones`` through
 the content-change handler.)

6. **D.04b — ``display(Markdown("…"))``** ( BUG-98-02
 fix) — set the source to ``from IPython.display import
 Markdown; Markdown("### display(Markdown) works\n\n`inline
 code`")`` and Run.
 - Assert: the output zone shows the **rendered** markdown —
 an ``<h3>`` heading, a ``<code>`` span — not the
 earlier ``<IPython.core.display.Markdown object>``
 repr. Screenshot: ``12-markdown-display-fixed.png``.

7. **D.07 — stderr + stdout mix** — set the source to ``import
 sys; sys.stderr.write("warning via stderr\n"); print("stdout
 line")`` and Run.
 - Assert: both lines appear in the output zone. The stderr
 line is rendered in the warning colour via the
 ``pql-nbedit-output-stderr`` CSS class (vs
 ``pql-nbedit-output-stream`` for stdout).
 Screenshot: ``07-stderr-stdout.png``.

8. **D.08 — traceback with frames** — set the source to a nested
 ``def inner(): raise ValueError("boom")`` /
 ``def outer(): inner()`` / ``outer()`` snippet and Run.
 - Assert: a multi-frame traceback renders with ``Cell In[N],
 line M, in outer()`` headers and the ANSI-coloured arrow
 markers (``----->``). The status pill flips to ``error``.
 Screenshot: ``08-traceback.png``.

9. **D.11 — ``IPython.display.HTML``** — set the source to an
 ``HTML`` call that emits a styled ``<div>``.
 - Assert: the div renders with its inline styles applied
 (background + border + bold inner span). The ``text/html``
 branch in ``output_renderer.js`` runs user-supplied HTML
 because the kernel is already trusted.
 Screenshot: ``11-html-display.png``.

10. **Save + on-disk inspection** — click Save.
 - Assert (shell): ``cat notebooks/sprint98_walkthrough.py``
 shows the jupytext frontmatter with
 ``cell_metadata_filter: -all`` and zero
 ``pql_cell_id`` tokens anywhere. A bare ``# %%`` marker
 is the only cell boundary.
 - ``grep -E '[0-9a-f]{8}-[0-9a-f]{4}'
 notebooks/sprint98_walkthrough.py`` returns nothing.

11. **Reload + output replay** — navigate away then back to the
 same editor URL.
 - Assert: the cells + their persisted outputs reappear. The
 server sends ``content_hash`` with each row;
 ``output_zone_manager.replayPersistedOutputs`` resolves
 the hash back to the session-local ``cell-N`` label using
 ``cellIdByContentHash`` and reanchors each output zone.
 - **Known:** rows whose ``content_hash`` no longer matches
 any live cell (user edited the source since the last run)
 are silently dropped — matches Databricks / VSCode
 orphan-output behaviour.

12. **External edit reload** — from another terminal,
 ``sed -i '1i# edited externally' notebooks/sprint98_walkthrough.py``
 and reload the browser.
 - Assert: the edit shows up; no 500 from the parser. The
 tolerance guards keep the editor open.

13. **Markerless file tolerance** — create a
 ``plain.py`` via ``/api/notebooks/create`` then write
 ``echo 'print(1)' > notebooks/plain.py`` from the shell
 and open ``/notebook/editor?path=plain.py``.
 - Assert: the file loads as a single code cell. ``Saved``
 flips to ``Pending`` immediately (dirty=True), and the
 next save normalises the file by inserting a ``# %%``
 header.

14. **BOM / CRLF tolerance** — from a shell, write a
 notebook with CRLF + leading BOM
 (``printf '\xef\xbb\xbf# %%\r\nx = 1\r\n' > notebooks/bom.py``)
 and open the editor.
 - Assert: cell source has no ``\ufeff`` prefix and no
 literal ``\r``. Immediate save rewrites the file as
 LF-only UTF-8.

## Bug tail

- **BUG-98-01** — markdown-cell view-zone preview misses its
 first paint after a synthetic ``setValue``. Real users
 hit the ``+ Markdown`` button (which fires content-change
 + ``rebuildMarkdownZones`` via the existing handler) so
 this is only observable in the Playwright path. Deferred.
- **BUG-98-02** — ``display(Markdown("…"))`` rendered the
 repr. **Fixed** by adding a ``text/markdown``
 branch to ``output_renderer.renderMimeBundle`` that
 re-uses the existing ``renderMarkdown`` helper.
- **BUG-98-05** — output zones keyed by the transient
 ``cell-N`` label accumulated as ghosts across
 ``setValue`` calls because ``rebuildCellAffordances``
 only pruned affordance widgets, not view zones. **Fixed**
 by adding ``pruneOrphanOutputZones(alive)``
 on the output-zone manager + calling it from
 ``main.js`` after every rebuild.
