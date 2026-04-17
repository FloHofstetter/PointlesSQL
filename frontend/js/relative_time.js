/*
 * PointlesSQL relative-time helper — extracted from Sprint 32 home.html
 * into its own file in Sprint 33 so /jobs rows can reuse it. Signature
 * and thresholds are unchanged; behaviour is identical so home.html's
 * latest-runs table still renders the same strings after the extraction.
 *
 * Usage:
 *   <span x-data="{ iso: '2024-01-01T00:00:00Z' }"
 *         x-text="pqlRelativeTime(iso)"></span>
 *
 * Returns the empty string for a missing iso, the raw iso for an
 * unparseable value, a coarse relative string for recent times, and
 * an ISO date (YYYY-MM-DD) for anything older than ~30 days.
 */
(function () {
    if (window.pqlRelativeTime) return;
    window.pqlRelativeTime = function (iso) {
        if (!iso) return '';
        const t = Date.parse(iso);
        if (Number.isNaN(t)) return iso;
        const delta = Math.max(0, (Date.now() - t) / 1000);
        if (delta < 45) return 'just now';
        if (delta < 90) return '1 min ago';
        if (delta < 3600) return Math.round(delta / 60) + ' min ago';
        if (delta < 5400) return '1 hour ago';
        if (delta < 86400) return Math.round(delta / 3600) + ' hours ago';
        if (delta < 129600) return '1 day ago';
        if (delta < 2592000) return Math.round(delta / 86400) + ' days ago';
        const d = new Date(t);
        return d.toISOString().slice(0, 10);
    };
})();
