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

import { CELL_MARKER_RE } from './cell_parser.js';
import { parseMarkerTag } from './cell_types.js';

export function currentCellAtCursor(editor, model) {
    if (!editor || !model) return null;
    const pos = editor.getPosition();
    if (!pos) return null;
    const above = model.getValueInRange({
        startLineNumber: 1, startColumn: 1,
        endLineNumber: pos.lineNumber, endColumn: model.getLineMaxColumn(pos.lineNumber),
    }).split('\n');
    for (let i = above.length - 1; i >= 0; i--) {
        const m = above[i].match(CELL_MARKER_RE);
        if (m) return { id: m[2], cellType: parseMarkerTag(m[1]) };
    }
    return null;
}

export function cellTypeOf(model, cellId) {
    if (!model) return 'code';
    const lines = model.getValue().split('\n');
    for (const line of lines) {
        const m = line.match(CELL_MARKER_RE);
        if (m && m[2] === cellId) return parseMarkerTag(m[1]);
    }
    return 'code';
}

export function cellSourceById(model, cellId) {
    const lines = model.getValue().split('\n');
    const out = [];
    let collecting = false;
    for (const line of lines) {
        const m = line.match(CELL_MARKER_RE);
        if (m) {
            if (m[2] === cellId) { collecting = true; continue; }
            if (collecting) break;
        } else if (collecting) {
            out.push(line);
        }
    }
    return out.join('\n');
}

// Sprint 71: read the ``result_var`` segment from the marker line for
// SQL cells.  Returns ``null`` for non-SQL cells or SQL cells with no
// segment / an invalid identifier.
export function cellResultVarById(model, cellId) {
    if (!model) return null;
    const lines = model.getValue().split('\n');
    for (const line of lines) {
        const m = line.match(CELL_MARKER_RE);
        if (m && m[2] === cellId) {
            if (parseMarkerTag(m[1]) !== 'sql') return null;
            return m[3] || null;
        }
    }
    return null;
}

export function cellEndLine(model, cellId) {
    const lines = model.getValue().split('\n');
    let start = null;
    for (let i = 0; i < lines.length; i++) {
        const m = lines[i].match(CELL_MARKER_RE);
        if (m) {
            if (start !== null) return i;
            if (m[2] === cellId) start = i + 1;
        }
    }
    return start !== null ? lines.length : null;
}

export function findCellMarkerLine(model, cellId) {
    const lines = model.getValue().split('\n');
    for (let i = 0; i < lines.length; i++) {
        const m = lines[i].match(CELL_MARKER_RE);
        if (m && m[2] === cellId) return i + 1;
    }
    return 1;
}
