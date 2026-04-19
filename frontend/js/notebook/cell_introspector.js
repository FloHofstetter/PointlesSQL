// Phase 12.7 Sprint 75 — cell-introspection helpers carved out of main.js.
//
// These are stateless lookups against the live Monaco model: "where is
// the cursor?", "what type is cell X?", "what's the source of cell X?".
// Distinct from cell_parser.js (which is the source-text → cells split)
// because every helper here is Monaco/cursor-aware — they walk the live
// model line-by-line rather than working off a parsed snapshot.
//
// Pulled out so the orchestrator (main.js) does not have to carry ~100
// lines of regex-driven model walks.  No closure state, no factory —
// callers pass the editor / model explicitly so the BUG-64-02 closure
// boundary stays in main.js where the Monaco refs are owned.
//
// Sprint 96: the on-disk marker grammar no longer carries a
// ``pql_cell_id="<uuid>"`` token.  Each helper therefore identifies
// cells by their **ordinal label** (``cell-0``, ``cell-1``, …) — the
// same shape :func:`splitCells` emits as the transient ``id`` field.
// The label is derived at scan time by counting ``# %%`` markers from
// the top of the file, so inserting / deleting cells renumbers every
// cell below the change point.  That is intended: the label is never
// persisted; its only purpose is stable DOM ref-keying within one
// session.  Content-hash identity (persistent across sessions, used
// in DB + WS keys) is computed by :func:`computeContentHash` on the
// cell's source text, independent of the label.

import { CELL_MARKER_RE, CELL_MARKER_LEGACY_RE } from './cell_parser.js';
import { parseMarkerTag } from './cell_types.js';

function _matchMarker(line) {
    return line.match(CELL_MARKER_RE) || line.match(CELL_MARKER_LEGACY_RE);
}

function _labelFor(index) {
    return `cell-${index}`;
}

export function currentCellAtCursor(editor, model) {
    if (!editor || !model) return null;
    const pos = editor.getPosition();
    if (!pos) return null;
    const lines = model.getValue().split('\n');
    let ordinal = -1;
    let lastMatch = null;
    for (let i = 0; i < lines.length; i++) {
        const m = _matchMarker(lines[i]);
        if (m) {
            ordinal += 1;
            if (i < pos.lineNumber) {
                lastMatch = { id: _labelFor(ordinal), cellType: parseMarkerTag(m[1]) };
            } else {
                break;
            }
        }
    }
    return lastMatch;
}

function _cellLineRangeByLabel(model, cellId) {
    const lines = model.getValue().split('\n');
    let ordinal = -1;
    let start = null;
    let end = lines.length;
    for (let i = 0; i < lines.length; i++) {
        const m = _matchMarker(lines[i]);
        if (!m) continue;
        ordinal += 1;
        const label = _labelFor(ordinal);
        if (start !== null) { end = i; break; }
        if (label === cellId) { start = i; }
    }
    if (start === null) return null;
    return { markerLine: start + 1, bodyStartIndex: start + 1, bodyEndIndex: end, lines };
}

export function cellTypeOf(model, cellId) {
    if (!model) return 'code';
    const range = _cellLineRangeByLabel(model, cellId);
    if (!range) return 'code';
    const m = _matchMarker(range.lines[range.markerLine - 1]);
    return m ? parseMarkerTag(m[1]) : 'code';
}

export function cellSourceById(model, cellId) {
    if (!model) return '';
    const range = _cellLineRangeByLabel(model, cellId);
    if (!range) return '';
    return range.lines.slice(range.bodyStartIndex, range.bodyEndIndex).join('\n');
}

// Sprint 71: read the ``result_var`` identifier from the marker line
// for SQL cells.  Returns ``null`` for non-SQL cells or SQL cells
// without an identifier segment.  Sprint 96 — the identifier lives
// positionally after the ``[sql]`` tag (``# %% [sql] df``), no longer
// as a named ``result_var="…"`` segment.  The legacy marker regex is
// also consulted so pre-Sprint-96 files still introspect correctly
// during the one-time migration save.
export function cellResultVarById(model, cellId) {
    if (!model) return null;
    const range = _cellLineRangeByLabel(model, cellId);
    if (!range) return null;
    const line = range.lines[range.markerLine - 1];
    const mNew = line.match(CELL_MARKER_RE);
    if (mNew) {
        if (parseMarkerTag(mNew[1]) !== 'sql') return null;
        return mNew[2] || null;
    }
    const mLegacy = line.match(CELL_MARKER_LEGACY_RE);
    if (mLegacy) {
        if (parseMarkerTag(mLegacy[1]) !== 'sql') return null;
        return mLegacy[3] || null;
    }
    return null;
}

export function cellEndLine(model, cellId) {
    if (!model) return null;
    const range = _cellLineRangeByLabel(model, cellId);
    return range ? range.bodyEndIndex : null;
}

export function findCellMarkerLine(model, cellId) {
    if (!model) return 1;
    const range = _cellLineRangeByLabel(model, cellId);
    return range ? range.markerLine : 1;
}
