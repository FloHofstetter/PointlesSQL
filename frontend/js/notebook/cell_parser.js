// Phase 12.7 Sprint 65 — cell-marker parser + namespace introspect snippet.
//
// Extracted unchanged from the Sprint-58 IIFE.  The serialiser
// (joinCells) and the parser (splitCells) are mirror operations; both
// honour the canonical ``# %% pql_cell_id="<uuid>"`` marker grammar
// the server's jupytext layer round-trips.  Foreign marker variants
// (# ---, # COMMAND ----------, # In[N]:) are accepted on the server
// load path but not re-emitted by the client.

// 1-based inclusive line ranges for each cell's *source* (marker
// line excluded so decorations colour only content).
export function joinCells(cells) {
    const lines = [];
    const ranges = [];
    for (let i = 0; i < cells.length; i++) {
        const cell = cells[i];
        const markerTag = cell.cell_type === 'markdown' ? ' [markdown]' : '';
        const marker = `# %%${markerTag} pql_cell_id="${cell.id}"`;
        if (i > 0) lines.push('');
        lines.push(marker);
        const bodyStart = lines.length + 1;
        const src = cell.source.length > 0 ? cell.source.split('\n') : [''];
        for (const line of src) lines.push(line);
        const bodyEnd = lines.length;
        ranges.push({ startLine: bodyStart, endLine: bodyEnd, cellType: cell.cell_type });
    }
    return { text: lines.join('\n'), cellRanges: ranges };
}

export function splitCells(text) {
    const lines = text.split('\n');
    const cells = [];
    let currentId = null;
    let currentType = 'code';
    let buffer = [];
    const flush = () => {
        if (currentId === null) return;
        // Strip the single trailing blank line joinCells emits between
        // cells so round-trips are byte-stable.
        if (buffer.length > 0 && buffer[buffer.length - 1] === '') {
            buffer.pop();
        }
        cells.push({ id: currentId, cell_type: currentType, source: buffer.join('\n') });
    };
    for (const line of lines) {
        const m = line.match(CELL_MARKER_RE);
        if (m) {
            flush();
            currentId = m[2];
            currentType = m[1] ? 'markdown' : 'code';
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

export const CELL_MARKER_RE = /^#\s*%%(\s+\[markdown\])?\s+pql_cell_id="([0-9a-fA-F-]{36})"\s*$/;

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
