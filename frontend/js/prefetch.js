// Phase 81.G.1 — prefetch links on hover.
//
// After ~80 ms of mouseover on a same-origin <a href>, inject
// <link rel="prefetch" href="..."> into <head> so the browser
// fetches the next page in the background.  Click then resolves
// from cache, making rail / breadcrumb / sidebar navigation feel
// instant.
//
// Skipped when:
//   * URL is cross-origin, has target=_blank, has download attr,
//     or starts with mailto: / tel: / javascript:
//   * The user has Data-Saver on (`navigator.connection.saveData`)
//     or is on slow-2g.
//   * Already prefetched in this session (WeakSet keyed by URL).
//
// Idempotent and HTMX-boost-compat: works fine on dynamic content
// inserted via hx-swap because the listener is attached to
// document, not to specific anchors.

(function () {
    const prefetched = new Set();
    let hoverTimer = null;

    function isSlowNetwork() {
        const c = navigator.connection;
        if (!c) return false;
        if (c.saveData) return true;
        const t = c.effectiveType;
        return t === 'slow-2g' || t === '2g';
    }

    function isPrefetchable(a) {
        if (!a || a.tagName !== 'A') return false;
        const href = a.getAttribute('href');
        if (!href) return false;
        if (a.target === '_blank' || a.hasAttribute('download')) return false;
        if (href.startsWith('#')) return false;
        if (href.startsWith('mailto:') || href.startsWith('tel:')) return false;
        if (href.startsWith('javascript:')) return false;
        // Resolve to absolute URL; only same-origin counts.
        let url;
        try {
            url = new URL(href, window.location.href);
        } catch (e) {
            return false;
        }
        if (url.origin !== window.location.origin) return false;
        // Skip API endpoints — prefetching JSON wastes bytes and
        // can interfere with CSRF / scope-protected routes.
        if (url.pathname.startsWith('/api/')) return false;
        if (url.pathname.startsWith('/static/')) return false;
        return url.href;
    }

    function prefetch(url) {
        if (prefetched.has(url)) return;
        prefetched.add(url);
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = url;
        link.as = 'document';
        document.head.appendChild(link);
    }

    function onMouseOver(ev) {
        if (isSlowNetwork()) return;
        const a = ev.target.closest('a[href]');
        if (!a) return;
        const url = isPrefetchable(a);
        if (!url) return;
        if (hoverTimer) clearTimeout(hoverTimer);
        hoverTimer = setTimeout(() => prefetch(url), 80);
    }

    function onMouseOut() {
        if (hoverTimer) {
            clearTimeout(hoverTimer);
            hoverTimer = null;
        }
    }

    document.addEventListener('mouseover', onMouseOver, { passive: true });
    document.addEventListener('mouseout', onMouseOut, { passive: true });
})();
