// Phase 12.7 Sprint 65 — ANSI → HTML span renderer for tracebacks.
//
// Jupyter error messages carry SGR colour codes straight out of
// IPython's ``ultratb`` formatter; we translate the common
// foreground colours, bold, and reset so the traceback reads as
// intended.  Anything we don't handle falls through as a stripped
// span — dependency-free, no xterm.js bundle.

const ANSI_ESCAPE_RE = /\x1B\[([0-9;]*)m/g;
const ANSI_FG = {
    30: '#6c757d', 31: '#e85050', 32: '#30c030', 33: '#d0a030',
    34: '#4080ff', 35: '#c050c0', 36: '#30c0c0', 37: '#d0d0d0',
    90: '#a0a0a0', 91: '#ff7070', 92: '#50e050', 93: '#ffd050',
    94: '#6090ff', 95: '#e070e0', 96: '#50d0d0', 97: '#ffffff',
};

export function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
}

export function ansiToHtml(text) {
    // Walk the string, closing/opening `<span>`s as SGR codes appear.
    // Round-trips multi-line tracebacks faithfully.
    let html = '';
    let openSpans = 0;
    let lastIndex = 0;
    text = text || '';
    let m;
    ANSI_ESCAPE_RE.lastIndex = 0;
    while ((m = ANSI_ESCAPE_RE.exec(text)) !== null) {
        html += escapeHtml(text.slice(lastIndex, m.index));
        lastIndex = ANSI_ESCAPE_RE.lastIndex;
        const codes = m[1] ? m[1].split(';').map(Number) : [0];
        for (const code of codes) {
            if (code === 0) {
                while (openSpans > 0) { html += '</span>'; openSpans--; }
            } else if (code === 1) {
                html += '<span style="font-weight:bold">';
                openSpans++;
            } else if (ANSI_FG[code]) {
                html += `<span style="color:${ANSI_FG[code]}">`;
                openSpans++;
            }
        }
    }
    html += escapeHtml(text.slice(lastIndex));
    while (openSpans > 0) { html += '</span>'; openSpans--; }
    return html;
}
