// Phase 12.7 Sprint 75 — Monaco view-zone lifecycle manager.
//
// Carved out of main.js (lines 881–1195 pre-Sprint-75).  Owns two
// per-cell view-zone maps:
//
//   outputZones[cellId]  → { zoneId, domNode }
//   markdownZones[cellId] → { zoneId, domNode, sourceRange, editModePinned }
//
// Both live in this factory's closure — same BUG-64-02 reactivity-
// boundary discipline as createClosureRefs.  Exposing them on Alpine's
// proxy would let the reactive deep-walk reach Monaco's internal zone
// registry and DOM nodes, reproducing the original Monaco hang.
//
// Distinct from output_renderer.js, which owns the mime-bundle
// rendering itself (pure DOM operations, no Monaco awareness).  This
// module is the bridge between cell ids, Monaco's zone API, and the
// renderer.

import { CELL_MARKER_RE } from './cell_parser.js';
import { parseMarkerTag } from './cell_types.js';
import { renderMarkdown } from './markdown.js';
import { appendOutputFrame } from './output_renderer.js';

export function createOutputZoneManager({ getEditor, getModel, getCellEndLine }) {
    const outputZones = {};
    const markdownZones = {};

    // ─────────────── output zones ───────────────

    function ensureOutputZone(cellId, afterLineNumber) {
        const editor = getEditor();
        let zone = outputZones[cellId];
        if (zone) {
            // Re-anchor if the cell's end line has shifted.
            editor.changeViewZones((accessor) => {
                accessor.removeZone(zone.zoneId);
                zone.zoneId = accessor.addZone({
                    afterLineNumber,
                    heightInPx: Math.max(zone.domNode.offsetHeight, 24),
                    domNode: zone.domNode,
                });
            });
            return zone.domNode;
        }
        const dom = document.createElement('div');
        dom.className = 'pql-nbedit-output';
        let zoneId = null;
        editor.changeViewZones((accessor) => {
            zoneId = accessor.addZone({
                afterLineNumber,
                heightInPx: 24,
                domNode: dom,
            });
        });
        outputZones[cellId] = { zoneId, domNode: dom };
        return dom;
    }

    function layoutOutputZone(cellId) {
        const zone = outputZones[cellId];
        if (!zone) return;
        getEditor().changeViewZones((accessor) => {
            accessor.layoutZone(zone.zoneId);
        });
    }

    function clearOutput(cellId) {
        const zone = outputZones[cellId];
        if (!zone) return;
        zone.domNode.innerHTML = '';
        layoutOutputZone(cellId);
    }

    function clearAllOutputs() {
        for (const cellId of Object.keys(outputZones)) {
            clearOutput(cellId);
        }
    }

    function appendOutput(cellId, msgType, content) {
        const endLine = getCellEndLine(cellId);
        if (endLine === null) return;
        const dom = ensureOutputZone(cellId, endLine);
        appendOutputFrame(dom, msgType, content);
        layoutOutputZone(cellId);
    }

    function replayPersistedOutputs(initialOutputs) {
        if (!initialOutputs || initialOutputs.length === 0) return;
        // Pick the latest kernel_session_id we see in the replay.  If
        // the current live WS session differs (hello arrives later) we
        // still paint the most recent persisted snapshot — the first
        // live execute will clear and re-emit.
        let latestSession = null;
        for (const row of initialOutputs) {
            if (!latestSession || row.kernel_session_id > latestSession) {
                latestSession = row.kernel_session_id;
            }
        }
        for (const row of initialOutputs) {
            if (row.kernel_session_id !== latestSession) continue;
            appendOutput(row.cell_id, row.msg_type, row.content);
        }
    }

    // ─────────── markdown preview zones + hidden-areas ───────────

    function rebuildMarkdownZones() {
        const editor = getEditor();
        const model = getModel();
        if (!editor || !model) return;
        const lines = model.getValue().split('\n');
        const cellList = [];
        let current = null;
        for (let i = 0; i < lines.length; i++) {
            const m = lines[i].match(CELL_MARKER_RE);
            if (m) {
                if (current) {
                    current.endLine = i;
                    cellList.push(current);
                }
                current = parseMarkerTag(m[1]) === 'markdown'
                    ? { id: m[2], markerLine: i + 1, sourceStart: i + 2, endLine: lines.length }
                    : null;
            }
        }
        if (current) cellList.push(current);

        const alive = new Set(cellList.map((c) => c.id));
        for (const cellId of Object.keys(markdownZones)) {
            if (!alive.has(cellId)) {
                const z = markdownZones[cellId];
                editor.changeViewZones((acc) => acc.removeZone(z.zoneId));
                delete markdownZones[cellId];
            }
        }

        for (const cell of cellList) {
            // Strip jupytext's leading "# " from each markdown body
            // line so the rendered markdown matches how the user sees
            // it in .ipynb tools.
            const body = cell.sourceStart <= cell.endLine
                ? lines.slice(cell.sourceStart - 1, cell.endLine)
                      .map((l) => l.replace(/^#\s?/, ''))
                      .join('\n')
                : '';
            let zone = markdownZones[cell.id];
            if (!zone) {
                const dom = document.createElement('div');
                dom.className = 'pql-nbedit-md-preview';
                dom.addEventListener('click', () => focusMarkdownSource(cell.id));
                let zoneId = null;
                editor.changeViewZones((acc) => {
                    zoneId = acc.addZone({
                        afterLineNumber: cell.markerLine,
                        heightInPx: 40,
                        domNode: dom,
                    });
                });
                zone = { zoneId, domNode: dom, editModePinned: false };
                markdownZones[cell.id] = zone;
            } else {
                editor.changeViewZones((acc) => {
                    acc.removeZone(zone.zoneId);
                    zone.zoneId = acc.addZone({
                        afterLineNumber: cell.markerLine,
                        heightInPx: Math.max(zone.domNode.offsetHeight, 40),
                        domNode: zone.domNode,
                    });
                });
            }
            zone.sourceRange = { startLine: cell.sourceStart, endLine: cell.endLine };
            zone.domNode.innerHTML = renderMarkdown(body)
                || '<em class="text-muted">Empty markdown cell — click to edit.</em>';
            editor.changeViewZones((acc) => acc.layoutZone(zone.zoneId));
        }
    }

    function focusMarkdownSource(cellId) {
        const zone = markdownZones[cellId];
        if (!zone || !zone.sourceRange) return;
        const editor = getEditor();
        editor.setPosition({
            lineNumber: zone.sourceRange.startLine,
            column: 1,
        });
        editor.focus();
        // setPosition fires onDidChangeCursorPosition which in turn
        // re-computes hidden areas, so the click-to-edit unhide is
        // automatic.
    }

    function updateHiddenAreas() {
        const editor = getEditor();
        if (!editor) return;
        const pos = editor.getPosition();
        const cursorLine = pos ? pos.lineNumber : 1;
        const hidden = [];
        for (const cellId of Object.keys(markdownZones)) {
            const z = markdownZones[cellId];
            if (!z.sourceRange) continue;
            // Sprint 69: a pinned cell stays unhidden regardless of
            // cursor position — the user explicitly clicked the pencil
            // to keep its source visible while typing elsewhere.
            if (z.editModePinned) continue;
            const { startLine, endLine } = z.sourceRange;
            if (cursorLine < startLine || cursorLine > endLine) {
                hidden.push({
                    startLineNumber: startLine,
                    endLineNumber: endLine,
                    startColumn: 1,
                    endColumn: 1,
                });
            }
        }
        // setHiddenAreas hides the ranges purely at the view layer —
        // the model (and therefore getValue() + save) stays intact.
        editor.setHiddenAreas(hidden);
    }

    // ─────────── markdown-zone read / mutate seam ───────────
    //
    // cell_affordances + the orchestrator's onTogglePin handler need
    // limited access to the markdown-zone records to mirror pin state
    // onto the toolbar widget.  Expose narrow methods rather than the
    // raw map so the closure boundary stays intact.

    function getMarkdownZone(cellId) {
        return markdownZones[cellId] || null;
    }

    function toggleMarkdownPin(cellId) {
        const zone = markdownZones[cellId];
        if (!zone) return null;
        zone.editModePinned = !zone.editModePinned;
        return zone.editModePinned;
    }

    return {
        ensureOutputZone,
        layoutOutputZone,
        clearOutput,
        clearAllOutputs,
        appendOutput,
        replayPersistedOutputs,
        rebuildMarkdownZones,
        focusMarkdownSource,
        updateHiddenAreas,
        getMarkdownZone,
        toggleMarkdownPin,
    };
}
