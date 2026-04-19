// Phase 12.7 Sprint 65 — cell-marker parser + namespace introspect snippet.
//
// Sprint 96 replaced the UUID-bearing marker grammar with a clean,
// positional shape that VSCode / Spyder / PyCharm already recognise:
//
//     ``# %%``              — code cell
//     ``# %% [markdown]``   — markdown cell
//     ``# %% [sql]``        — SQL cell without a result variable
//     ``# %% [sql] df``     — SQL cell binding its DataFrame to ``df``
//
// No ``pql_cell_id="…"`` sidecar. The client addresses cells by
// ``content_hash`` (``sha256(normalized_source)[:16]``) computed at
// parse time; ``splitCells`` returns a transient ordinal ``id``
// (``cell-0``, ``cell-1``, …) only for Alpine ``x-for :key``
// stability within the session.  Legacy pre-Sprint-96 files that
// still embed UUIDs parse through the fallback regex below and get
// normalised to the clean grammar on the next save — matching the
// one-way migration the Python ``notebook_doc.load_document`` path
// performs server-side.

import { getCellType, parseMarkerTag } from './cell_types.js';

// 1-based inclusive line ranges for each cell's *source* (marker
// line excluded so decorations colour only content).
export function joinCells(cells) {
    const lines = [];
    const ranges = [];
    for (let i = 0; i < cells.length; i++) {
        const cell = cells[i];
        const descriptor = getCellType(cell.cell_type);
        let marker = `# %%${descriptor.markerTag}`;
        // Sprint 96: SQL cells optionally carry a positional
        // ``result_var`` identifier appended after the ``[sql]`` tag
        // (``# %% [sql] df``). Round-trips stay byte-stable when the
        // field is missing — the segment is only emitted for SQL
        // cells whose ``resultVar`` is a non-empty Python identifier.
        if (descriptor.id === 'sql'
                && typeof cell.resultVar === 'string'
                && RESULT_VAR_RE.test(cell.resultVar)) {
            marker += ` ${cell.resultVar}`;
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

// Sprint 96: compute the 16-hex identity of a cell's normalized
// source. Mirrors ``compute_content_hash`` in
// ``pointlessql/services/notebook_doc.py`` — both sides implement
// FNV-1a 64-bit byte-for-byte so WS frames round-trip a cell
// identity between Python and the browser without either side
// needing async crypto. Synchronous so splitCells / rescan paths
// stay cheap to iterate.
const FNV_OFFSET_64 = 0xcbf29ce484222325n;
const FNV_PRIME_64 = 0x100000001b3n;
const FNV_MASK_64 = 0xffffffffffffffffn;

export function computeContentHash(source) {
    const normalized = (source || '')
        .replace(/\r\n/g, '\n')
        .split('\n')
        .map(line => line.replace(/\s+$/, ''))
        .join('\n');
    const bytes = new TextEncoder().encode(normalized);
    let h = FNV_OFFSET_64;
    for (const byte of bytes) {
        h = ((h ^ BigInt(byte)) * FNV_PRIME_64) & FNV_MASK_64;
    }
    return h.toString(16).padStart(16, '0');
}

export function splitCells(text) {
    const lines = text.split('\n');
    const cells = [];
    let seenMarker = false;
    let currentType = 'code';
    let currentResultVar = null;
    let buffer = [];
    const flush = () => {
        if (!seenMarker) return;
        // Strip the single trailing blank line joinCells emits between
        // cells so round-trips are byte-stable.
        if (buffer.length > 0 && buffer[buffer.length - 1] === '') {
            buffer.pop();
        }
        const source = buffer.join('\n');
        cells.push({
            id: `cell-${cells.length}`,
            content_hash: computeContentHash(source),
            cell_type: currentType,
            source,
            resultVar: currentResultVar,
        });
    };
    for (const line of lines) {
        const newMatch = line.match(CELL_MARKER_RE);
        const legacyMatch = !newMatch ? line.match(CELL_MARKER_LEGACY_RE) : null;
        const match = newMatch || legacyMatch;
        if (match) {
            flush();
            seenMarker = true;
            if (newMatch) {
                currentType = parseMarkerTag(newMatch[1]);
                currentResultVar = currentType === 'sql' && newMatch[2]
                    ? newMatch[2]
                    : null;
            } else {
                currentType = parseMarkerTag(legacyMatch[1]);
                currentResultVar = currentType === 'sql' && legacyMatch[3]
                    ? legacyMatch[3]
                    : null;
            }
            buffer = [];
        } else if (seenMarker) {
            buffer.push(line);
        }
        // Lines before the first marker are discarded — jupytext
        // treats them as file-level frontmatter, which the skeleton
        // does not yet let the user edit.
    }
    flush();
    return cells;
}

// Sprint 96 new grammar:
// Group 1 captures the full ``[tag]`` segment (with leading space).
// Group 2 captures the optional positional SQL ``result_var``
// identifier after the tag.  ``parseMarkerTag`` in ``cell_types.js``
// resolves group 1 to a registry id and falls back to ``code`` for
// unknown tags.
export const CELL_MARKER_RE = /^#\s*%%(\s+\[\w+\])?(?:\s+([A-Za-z_][A-Za-z0-9_]*))?\s*$/;

// Sprint 96 legacy fallback: accepts pre-migration
// ``# %% [tag?] pql_cell_id="<uuid>" result_var="<name>"`` markers so
// notebooks saved before the grammar change still load cleanly. The
// next save normalises them to the clean grammar above.
export const CELL_MARKER_LEGACY_RE = /^#\s*%%(\s+\[\w+\])?\s+pql_cell_id="([0-9a-fA-F-]{36})"(?:\s+result_var="([A-Za-z_][A-Za-z0-9_]*)")?\s*$/;

// Sprint 71: client-side validator for the result_var input shown on
// SQL cells.  Mirrors the regex group above; centralised so the
// affordance and the serialiser agree on the rule.
export const RESULT_VAR_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

// Sprint 62 namespace introspect.  Runs inside the user's kernel
// under content_hash=__pql_namespace__; the persistence layer + the
// client's output renderer both filter that identity so it never
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
