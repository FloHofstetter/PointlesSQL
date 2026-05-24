// PointlesSQL copy-to-clipboard button.
//
// Single delegated listener for every `.pql-copy-btn` on the page.
// Reads the value from the button's ``data-pql-copy`` attribute,
// writes to the clipboard via the async Clipboard API, and surfaces
// success/failure via ``window.pqlToast``.
//
// bootstrap.js imports this module so the listener is registered
// once at app start.  No per-button init cost — safe to render
// hundreds of buttons inside a list-table.

function setupCopyButtons() {
    document.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('.pql-copy-btn');
        if (!btn) return;
        ev.preventDefault();
        const value = btn.dataset.pqlCopy ?? '';
        if (!value) return;
        try {
            await navigator.clipboard.writeText(value);
            const label = btn.getAttribute('aria-label') || 'Copy';
            window.pqlToast?.success?.(`${label} — copied.`);
        } catch (err) {
            window.pqlToast?.error?.(`Copy failed: ${err.message || err}`);
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupCopyButtons);
} else {
    setupCopyButtons();
}

export { setupCopyButtons };
