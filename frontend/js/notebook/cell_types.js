// Phase 12.7 Sprint 66 — cell-type registry.
//
// Replaces the Sprint-58 hardcoded ``code | markdown`` branches that
// spread across cell_parser.js and main.js.  A cell type is a plain
// object descriptor; adding a new type (Sprint 71's ``sql``) means
// registering one entry — the parser, runners, decorations, and
// affordances all pick it up from ``getCellType(id)``.
//
// Descriptors are module-scoped plain objects, never passed into
// Alpine's reactive proxy.  Same pattern as NAMESPACE_INTROSPECT_CODE
// in cell_parser.js.

export const cellTypeRegistry = {
    code: {
        id: 'code',
        label: 'Python',
        markerTag: '',
        canExecute: true,
        bandClass: 'pql-nbedit-cell-band-code',
    },
    markdown: {
        id: 'markdown',
        label: 'Markdown',
        markerTag: ' [markdown]',
        canExecute: false,
        bandClass: 'pql-nbedit-cell-band-markdown',
        // Sprint 69: opt into the per-cell pencil button that pins
        // the cell into source view independently of cursor position.
        affordances: ['pin'],
    },
};

// Fall back to ``code`` on unknown ids so forward-compat tags
// (e.g. ``[sql]`` loaded by a client that predates Sprint 71) render
// as a plain code cell instead of crashing the editor.
export function getCellType(id) {
    return cellTypeRegistry[id] || cellTypeRegistry.code;
}

// Parse the bracket segment of a cell marker into a type id.
// Input: either the full ``" [markdown]"`` match, the inner
// ``"markdown"``, or an empty / missing value (→ ``"code"``).
export function parseMarkerTag(tag) {
    if (!tag) return 'code';
    const trimmed = String(tag).trim().replace(/^\[|\]$/g, '');
    return cellTypeRegistry[trimmed] ? trimmed : 'code';
}
