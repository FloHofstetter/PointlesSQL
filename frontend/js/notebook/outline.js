// Phase 12.7 Sprint 70 — outline / TOC extractor.
//
// Pure leaf module: takes the closure-local ``cells`` array
// (shape ``{ id, cell_type, source }[]``, straight from
// ``cell_parser.js::splitCells``) and returns a flat list of
// outline entries for the right-side Outline panel.
//
// Why a regex pass and not a markdown-it token walk:
// Sprint 69's markdown-it vendor bundle hit BUG-69-01 (UMD wrappers
// detect Monaco's AMD ``window.define`` and collide with Monaco's
// "one anonymous define per script" contract).  Keeping the
// outline extractor zero-dep isolates it from that loader-order
// landmine and from any future markdown-it / KaTeX churn — the
// outline still renders when markdown-it fails to load.
//
// Why not a ``cell_types`` registry affordance: the Sprint-69
// ``affordances: ['pin']`` pattern models per-cell UI (Monaco
// content widgets / view zones).  The outline is cross-cell
// aggregated — a singleton right-sidebar list — so it does not
// plug into the per-cell affordance seam.
//
// Why stateless: this module is re-entrant and idempotent.
// Callers own the closure ``cells`` snapshot; every call produces
// a fresh array.  No closure ``let``s, no caches, no side effects.

const HEADING_RE = /^(#{1,3})\s+(.+?)\s*$/;
const CODE_LABEL_LIMIT = 60;

export function stripCodeLabel(line) {
    let out = (line ?? '').trim();
    if (out.startsWith('# ')) {
        out = out.slice(2).trim();
    } else if (out === '#') {
        out = '';
    }
    if (out.length > CODE_LABEL_LIMIT) {
        out = out.slice(0, CODE_LABEL_LIMIT - 1) + '\u2026';
    }
    return out;
}

export function buildOutline(cells) {
    const out = [];
    if (!Array.isArray(cells)) return out;
    for (const cell of cells) {
        if (!cell || typeof cell.id !== 'string') continue;
        const source = typeof cell.source === 'string' ? cell.source : '';
        if (cell.cell_type === 'markdown') {
            // The server unwraps jupytext's ``# `` comment-prefix
            // from markdown cell source before sending the bundle,
            // so ``source`` is already raw markdown — a fresh
            // ``## Sub`` here is a real H2, not ``# ## Sub`` that
            // needs another strip.  Stripping again would shift
            // every heading down by one level.
            for (const line of source.split('\n')) {
                const m = line.match(HEADING_RE);
                if (!m) continue;
                out.push({
                    cellId: cell.id,
                    kind: 'heading',
                    level: m[1].length,
                    label: m[2].trim(),
                });
            }
        } else {
            let firstLine = '';
            for (const line of source.split('\n')) {
                if (line.trim() !== '') { firstLine = line; break; }
            }
            const label = stripCodeLabel(firstLine);
            out.push({
                cellId: cell.id,
                kind: 'code',
                level: 0,
                label: label === '' ? '(empty cell)' : label,
            });
        }
    }
    return out;
}
