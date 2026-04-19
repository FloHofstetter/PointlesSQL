// Phase 12.7 Sprint 65 — cell-marker parser + namespace introspect snippet.
//
// Sprint 66 widened the marker regex to accept any bracket tag (e.g.
// ``[markdown]``, ``[sql]``) and delegated tag→type resolution to
// ``cell_types.js``'s ``parseMarkerTag`` / ``getCellType``.  The
// serialiser (``joinCells``) and parser (``splitCells``) stay mirror
// operations; both honour the canonical
// ``# %% [tag?] pql_cell_id="<uuid>"`` grammar that soyuz-catalog's
// jupytext layer round-trips.  Foreign marker variants (# ---,
// # COMMAND ----------, # In[N]:) are accepted on the server load
// path but not re-emitted by the client.

import { getCellType, parseMarkerTag } from './cell_types.js';

// 1-based inclusive line ranges for each cell's *source* (marker
// line excluded so decorations colour only content).
export function joinCells(cells) {
    const lines = [];
    const ranges = [];
    for (let i = 0; i < cells.length; i++) {
        const cell = cells[i];
        const descriptor = getCellType(cell.cell_type);
        let marker = `# %%${descriptor.markerTag} pql_cell_id="${cell.id}"`;
        // Sprint 71: SQL cells optionally carry a ``result_var``
        // segment.  Round-trips stay byte-stable when the field is
        // missing — the segment is only emitted for SQL cells whose
        // ``resultVar`` is a non-empty Python identifier.
        if (descriptor.id === 'sql'
                && typeof cell.resultVar === 'string'
                && RESULT_VAR_RE.test(cell.resultVar)) {
            marker += ` result_var="${cell.resultVar}"`;
        }
        if (i > 0) lines.push('');
        lines.push(marker);
        const bodyStart = lines.length + 1;
        const src = cell.source.length > 0 ? cell.source.split('\n') : [''];
        for (const line of src) lines.push(line);
        const bodyEnd = lines.length;
        ranges.push({ startLine: bodyStart, endLine: bodyEnd, cellType: descriptor.id });
    }
    return { text: lines.join('\n'), cellRanges: ranges };
}

export function splitCells(text) {
    const lines = text.split('\n');
    const cells = [];
    let currentId = null;
    let currentType = 'code';
    let currentResultVar = null;
    let buffer = [];
    const flush = () => {
        if (currentId === null) return;
        // Strip the single trailing blank line joinCells emits between
        // cells so round-trips are byte-stable.
        if (buffer.length > 0 && buffer[buffer.length - 1] === '') {
            buffer.pop();
        }
        cells.push({
            id: currentId,
            cell_type: currentType,
            source: buffer.join('\n'),
            resultVar: currentResultVar,
        });
    };
    for (const line of lines) {
        const m = line.match(CELL_MARKER_RE);
        if (m) {
            flush();
            currentId = m[2];
            currentType = parseMarkerTag(m[1]);
            // Sprint 71: ``result_var`` belongs to SQL cells; keep it
            // null on every other type so the per-cell shape stays
            // predictable for outline.js / cell_affordances.js.
            currentResultVar = currentType === 'sql' && m[3] ? m[3] : null;
            buffer = [];
        } else if (currentId !== null) {
            buffer.push(line);
        }
        // Lines before the first marker are discarded — jupytext
        // treats them as file-level frontmatter, which the skeleton
        // does not yet let the user edit.
    }
    flush();
    return cells;
}

// Group 1 captures the full ``[tag]`` segment (with leading space);
// group 2 captures the cell UUID.  ``parseMarkerTag`` in
// ``cell_types.js`` resolves group 1 to a registry id and falls back
// to ``code`` for unknown tags.  Sprint 71 widens the regex with an
// optional ``result_var="<ident>"`` segment (group 3); the
// constraint matches a Python identifier so the kernel can bind it
// directly into ``globals()`` without further validation.
export const CELL_MARKER_RE = /^#\s*%%(\s+\[\w+\])?\s+pql_cell_id="([0-9a-fA-F-]{36})"(?:\s+result_var="([A-Za-z_][A-Za-z0-9_]*)")?\s*$/;

// Sprint 71: client-side validator for the result_var input shown on
// SQL cells.  Mirrors the regex group above; centralised so the
// affordance and the serialiser agree on the rule.
export const RESULT_VAR_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

// Sprint 62 namespace introspect.  Runs inside the user's kernel
// under cell_id=__pql_namespace__; the persistence layer + the
// client's output renderer both filter that cell_id so it never
// pollutes the notebook UI.  Payload: name → {type, shape, repr,
// preview_html}.
export const NAMESPACE_INTROSPECT_CODE = [
    'def _pql_introspect():',
    '    import json',
    '    out = {}',
    '    try:',
    '        g = globals()',
    '    except NameError:',
    '        return json.dumps({})',
    '    skip = {"In", "Out", "exit", "quit", "get_ipython", "_pql_introspect"}',
    '    for name, val in list(g.items()):',
    '        if name.startswith("_") or name in skip:',
    '            continue',
    '        if callable(val) and getattr(val, "__module__", "") in (',
    '                "builtins", "IPython.core.interactiveshell"):',
    '            continue',
    '        try:',
    '            tname = type(val).__name__',
    '            module = getattr(type(val), "__module__", "")',
    '            if module and module not in ("builtins",):',
    '                tname = module.split(".")[0] + "." + tname',
    '        except Exception:',
    '            tname = "?"',
    '        shape = None',
    '        try:',
    '            if hasattr(val, "shape"):',
    '                shape = list(getattr(val, "shape"))',
    '            elif isinstance(val, (list, tuple, set, dict)):',
    '                shape = [len(val)]',
    '        except Exception:',
    '            shape = None',
    '        preview_html = None',
    '        try:',
    '            if tname.endswith("DataFrame") and hasattr(val, "head"):',
    '                preview_html = val.head().to_html(classes="pql-nbedit-vars-df", border=0)',
    '        except Exception:',
    '            preview_html = None',
    '        repr_ = None',
    '        if preview_html is None:',
    '            try:',
    '                repr_ = repr(val)',
    '                if len(repr_) > 200: repr_ = repr_[:197] + "..."',
    '            except Exception:',
    '                repr_ = "<unrepresentable>"',
    '        out[name] = {"type": tname, "shape": shape, "preview_html": preview_html, "repr": repr_}',
    '    return json.dumps(out)',
    'print(_pql_introspect())',
].join('\n');
