// Phase 12.7 Sprint 69 — markdown-it + KaTeX preview renderer.
//
// Replaces the Sprint-65 regex pass with a CommonMark-conformant
// renderer (tables, nested lists, task lists, autolinking).  KaTeX
// math is layered via markdown-it-texmath using the ``dollars``
// delimiter set: ``$inline$`` and ``$$block$$``.
//
// All three libs are loaded as UMD ``<script>`` globals from
// notebook_editor.html before this module is import()-ed; we look
// them up off ``window`` lazily on first call so the module can be
// imported in test contexts that do not load Monaco's HTML.
//
// KaTeX is independently droppable per the Phase-12.7 trim policy:
// removing the ``.use(window.texmath, …)`` line below and the three
// matching ``<script>`` / ``<link>`` tags in notebook_editor.html
// reverts to plain markdown-it without breaking anything else.

let mdSingleton = null;

function getMd() {
    if (mdSingleton) return mdSingleton;
    if (typeof window === 'undefined' || !window.markdownit) {
        return null;
    }
    const md = window.markdownit({
        // ``html: false`` preserves the Sprint-65 escape posture —
        // raw HTML in cell source is rendered as text, not parsed.
        html: false,
        linkify: true,
        breaks: true,
    });
    if (window.texmath && window.katex) {
        md.use(window.texmath, {
            engine: window.katex,
            delimiters: 'dollars',
            katexOptions: { throwOnError: false },
        });
    }
    // Open links in a new tab — matches the Sprint-65 anchor target.
    const defaultLinkOpen = md.renderer.rules.link_open
        || ((tokens, idx, opts, _env, self) => self.renderToken(tokens, idx, opts));
    md.renderer.rules.link_open = (tokens, idx, opts, env, self) => {
        const tok = tokens[idx];
        if (tok.attrIndex('target') < 0) tok.attrPush(['target', '_blank']);
        if (tok.attrIndex('rel') < 0) tok.attrPush(['rel', 'noopener']);
        return defaultLinkOpen(tokens, idx, opts, env, self);
    };
    mdSingleton = md;
    return mdSingleton;
}

export function renderMarkdown(src) {
    const md = getMd();
    if (!md) return '';
    return md.render(src ?? '');
}
