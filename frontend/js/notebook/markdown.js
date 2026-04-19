// Phase 12.7 Sprint 65 — minimal markdown renderer for view-zone preview.
//
// Covers the common cell shapes: headings, paragraphs, bold / italic,
// inline code, code fences, links, single-level bullet lists.  The
// view zone is a preview target, users always retain the raw source
// (cursor-enters-cell unhides it).  HTML in the source passes through
// — same trust model as cell output HTML.
//
// Sprint 69 swaps this for ``markdown-it`` + KaTeX; the regex
// implementation here keeps Sprint 65 dependency-free.

import { escapeHtml } from './ansi.js';

export function renderMarkdown(src) {
    if (!src) return '';
    // Fenced code blocks first, so their inner text is not subject
    // to later inline-markdown passes.  We tag them with a placeholder
    // and re-inject after the inline pass.
    const fences = [];
    src = src.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)\n?```/g, (_, _lang, code) => {
        const idx = fences.length;
        fences.push(`<pre class="pql-nbedit-md-code"><code>${escapeHtml(code)}</code></pre>`);
        return `\u0000FENCE${idx}\u0000`;
    });
    // Headings (leading #'s must start at column 0)
    src = src.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>');
    src = src.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>');
    src = src.replace(/^####\s+(.+)$/gm, '<h5>$1</h5>');
    src = src.replace(/^###\s+(.+)$/gm, '<h5>$1</h5>');
    src = src.replace(/^##\s+(.+)$/gm, '<h4>$1</h4>');
    src = src.replace(/^#\s+(.+)$/gm, '<h3>$1</h3>');
    // Bold + italic (non-greedy, avoid eating ** inside code)
    src = src.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    src = src.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>');
    // Inline code
    src = src.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    // Links [text](url)
    src = src.replace(/\[([^\]]+)\]\(([^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener">$1</a>');
    // Simple bullet lists — one level only
    src = src.replace(/^(?:-|\*)\s+(.+)$/gm, '<li>$1</li>');
    src = src.replace(/(<li>[^\n]+<\/li>(?:\n<li>[^\n]+<\/li>)*)/g, '<ul>$1</ul>');
    // Paragraphs: split on blank lines, leave block-level tags alone.
    const paragraphs = src.split(/\n{2,}/).map((block) => {
        const trimmed = block.trim();
        if (!trimmed) return '';
        if (/^\u0000FENCE\d+\u0000$/.test(trimmed)) return trimmed;
        if (/^<(h[1-6]|ul|ol|pre|blockquote)/.test(trimmed)) return block;
        return `<p>${block.replace(/\n/g, '<br>')}</p>`;
    });
    let out = paragraphs.join('\n');
    // Re-inject fences
    out = out.replace(/\u0000FENCE(\d+)\u0000/g, (_, idx) => fences[Number(idx)]);
    return out;
}
