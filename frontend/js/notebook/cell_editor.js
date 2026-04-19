// Sprint 76 — cell mutation operations carved out of main.js.
//
// Four operations that all rewrite the Monaco model in place:
//   - insertCellAfter(afterCellId, typeId): new cell directly after an anchor
//   - addCellBelow(): new code cell at end of document
//   - addCellAbove(markdown): new cell just above the cursor's current cell
//   - applyResultVarToMarker(cellId, name): rewrite a SQL cell's marker line
//                                           to add / update / drop the
//                                           positional result_var identifier
//
// None of them touch ``this`` or Alpine state — they operate purely on
// the Monaco editor/model behind ``refs`` plus ``window.monaco``.  The
// caller re-runs ``rescanDecorations`` after insert/add ops so the
// cell-band gutter + affordances rebuild; the result-var op is a pure
// marker-line edit that doesn't change cell boundaries, so it skips the
// rescan.
//
// Sprint 96: marker grammar dropped the per-cell UUID.  The inserter
// ops therefore emit clean ``# %%`` / ``# %% [markdown]`` / ``# %% [sql]``
// markers with no ``pql_cell_id="…"`` segment; applyResultVarToMarker
// switches from the named ``result_var="…"`` shape to the positional
// ``# %% [sql] df`` shape the parser and server now round-trip.

import { CELL_MARKER_RE, CELL_MARKER_LEGACY_RE } from './cell_parser.js';
import { getCellType, parseMarkerTag } from './cell_types.js';
import {
    cellEndLine as introspectCellEndLine,
    findCellMarkerLine as introspectFindCellMarkerLine,
    currentCellAtCursor as introspectCurrentCellAtCursor,
} from './cell_introspector.js';

export function createCellEditor({ refs, rescanDecorations }) {
    function insertCellAfter(afterCellId, typeId) {
        const model = refs.get('model');
        const editor = refs.get('editor');
        const monaco = window.monaco;
        if (!model || !editor || !monaco) return;
        const descriptor = getCellType(typeId);
        const marker = `\n# %%${descriptor.markerTag}\n\n`;
        const endLine = introspectCellEndLine(model, afterCellId);
        const anchorLine = endLine === null ? model.getLineCount() : endLine;
        const anchorCol = model.getLineMaxColumn(anchorLine);
        editor.executeEdits('pql-insert-after', [{
            range: new monaco.Range(anchorLine, anchorCol, anchorLine, anchorCol),
            text: marker,
            forceMoveMarkers: true,
        }]);
        rescanDecorations();
        editor.focus();
    }

    function addCellBelow() {
        const model = refs.get('model');
        const editor = refs.get('editor');
        if (!model || !editor) return;
        const marker = `\n\n# %%${getCellType('code').markerTag}\n`;
        const lastLine = model.getLineCount();
        const lastCol = model.getLineMaxColumn(lastLine);
        editor.executeEdits('add-cell', [{
            range: new window.monaco.Range(lastLine, lastCol, lastLine, lastCol),
            text: marker,
            forceMoveMarkers: true,
        }]);
        rescanDecorations();
    }

    function addCellAbove(markdown) {
        const cell = introspectCurrentCellAtCursor(refs.get('editor'), refs.get('model'));
        const monaco = window.monaco;
        const editor = refs.get('editor');
        const tag = markdown ? getCellType('markdown').markerTag : getCellType('code').markerTag;
        const marker = `# %%${tag}\n\n`;
        const targetLine = cell ? introspectFindCellMarkerLine(refs.get('model'), cell.id) : 1;
        const insertAt = new monaco.Range(targetLine, 1, targetLine, 1);
        editor.executeEdits('add-cell-above', [{
            range: insertAt, text: marker, forceMoveMarkers: true,
        }]);
        editor.setPosition({ lineNumber: targetLine + 1, column: 1 });
        rescanDecorations();
    }

    function applyResultVarToMarker(cellId, name) {
        const editor = refs.get('editor');
        const model = refs.get('model');
        const monaco = window.monaco;
        if (!editor || !model || !monaco) return;
        const lineNumber = introspectFindCellMarkerLine(model, cellId);
        const lineText = model.getLineContent(lineNumber);
        // Accept either grammar on read so a legacy-file edit doesn't
        // no-op before its migration save.
        const m = lineText.match(CELL_MARKER_RE) || lineText.match(CELL_MARKER_LEGACY_RE);
        if (!m || parseMarkerTag(m[1]) !== 'sql') return;
        let newLine = '# %% [sql]';
        if (name) newLine += ` ${name}`;
        if (newLine === lineText) return;
        const range = new monaco.Range(
            lineNumber, 1, lineNumber, model.getLineMaxColumn(lineNumber),
        );
        editor.executeEdits('result-var-edit', [{ range, text: newLine, forceMoveMarkers: true }]);
    }

    return { insertCellAfter, addCellBelow, addCellAbove, applyResultVarToMarker };
}
