// Sprint 76 — cell-range scanner + decoration factory carved out of main.js.
//
// Pure functions only.  ``scanCellRanges`` walks the Monaco model's text
// for ``# %% …`` markers and returns the line ranges per cell-type;
// ``rangesToDecorations`` converts those ranges into the Monaco
// deltaDecorations payload.  No closure state, no refs — callers hold
// the decoration ID list themselves and feed it to deltaDecorations.

import { CELL_MARKER_RE } from './cell_parser.js';
import { getCellType, parseMarkerTag } from './cell_types.js';

export function scanCellRanges(model) {
    const lines = model.getValue().split('\n');
    const ranges = [];
    let currentStart = null;
    let currentType = 'code';
    for (let i = 0; i < lines.length; i++) {
        const m = lines[i].match(CELL_MARKER_RE);
        if (m) {
            if (currentStart !== null) {
                ranges.push({ startLine: currentStart, endLine: i, cellType: currentType });
            }
            currentType = parseMarkerTag(m[1]);
            currentStart = i + 2;
        }
    }
    if (currentStart !== null) {
        ranges.push({ startLine: currentStart, endLine: lines.length, cellType: currentType });
    }
    return ranges;
}

export function rangesToDecorations(monaco, ranges) {
    return ranges.map((r) => ({
        range: new monaco.Range(r.startLine, 1, r.endLine, 1),
        options: {
            isWholeLine: true,
            className: getCellType(r.cellType).bandClass,
        },
    }));
}
