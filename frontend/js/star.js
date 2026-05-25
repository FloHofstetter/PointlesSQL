// Starred-items Alpine factory.  Reusable x-data wrapping
// a star-toggle button on catalog / schema / table detail pages.
// Stored in workspace-namespaced ``pql.starred.<slug>`` as a
// mixed-kind array; sidebar reads the same array and renders
// the appropriate icon + URL per kind.  Broadcasts
// ``pql:starred-changed`` so the open sidebar picks up changes
// without a hard reload.
//
// D lifted this out of base.html so the layout file
// shrinks below 750 lines and the factory gets a single grep-able
// home shared by every page that mounts a star toggle.
//
// payload shape:
//   { kind: 'catalog', name }
//   { kind: 'schema',  catalog, schema }
//   { kind: 'table',   catalog, schema, table }
//   { kind: 'model'/'branch'/'run'/...,  ref }   (server-backed)

// Starred-items Alpine factory.  Reusable x-data wrapping
// a star-toggle button on catalog / schema / table detail pages.
// Stored in workspace-namespaced ``pql.starred.<slug>`` as a
// mixed-kind array; sidebar reads the same array and renders
// the appropriate icon + URL per kind.  Broadcasts
// ``pql:starred-changed`` so the open sidebar picks up changes
// without a hard reload.
//
// payload shape:
//   { kind: 'catalog', name }
//   { kind: 'schema',  catalog, schema }
//   { kind: 'table',   catalog, schema, table }
window.pqlStarKey = function (item) {
    if (!item || !item.kind) return '';
    if (item.kind === 'catalog') return 'cat:' + item.name;
    if (item.kind === 'schema') return 'sch:' + item.catalog + '.' + item.schema;
    if (item.kind === 'table') {
        return 'tbl:' + (item.ref || (item.catalog + '.' + item.schema + '.' + item.table));
    }
    // generic shape: any kind that the social registry
    // recognises (model / branch / run / dp / table / …) uses
    // ``{kind, ref}``; keep a stable key so the localStorage fallback
    // path (for catalog + schema kinds until 77.5) doesn't double-key.
    if (item.ref) return item.kind + ':' + item.ref;
    return '';
};
// pqlStarToggle is now server-backed for every
// entity kind registered in the social entity_registry; for
// kinds that aren't yet registered (catalog + schema) the
// component gracefully degrades to localStorage so the
// existing schemas.html / tables.html buttons keep working
// unchanged.
//
// Payload shapes accepted:
//   { kind: 'table',  ref: 'cat.sch.tbl' }            (new canonical)
//   { kind: 'table',  catalog, schema, table }        (legacy)
//   { kind: 'schema', catalog, schema }               (legacy → localStorage)
//   { kind: 'catalog', name }                         (legacy → localStorage)
//   { kind: 'model'/'branch'/'run', ref: '...' }      (server)
//
// The component reads its initial state on init() so star
// counts + the caller's starred flag survive page reloads
// across devices.
window.pqlStarToggle = function (payload) {
    const slugMeta = document.querySelector('meta[name="workspace-slug"]');
    const slug = slugMeta && slugMeta.content ? slugMeta.content : 'default';
    const KEY = 'pql.starred.' + slug;
    const kind = payload && payload.kind;
    const ref = (payload && payload.ref) ||
                (kind === 'table' && payload.catalog && payload.schema && payload.table
                    ? `${payload.catalog}.${payload.schema}.${payload.table}`
                    : null);
    const useServer = !!(kind && ref);
    const myKey = window.pqlStarKey(payload);

    function readLocal() {
        try {
            const raw = localStorage.getItem(KEY);
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) { return []; }
    }
    function writeLocal(items) {
        try {
            localStorage.setItem(KEY, JSON.stringify(items));
            window.dispatchEvent(new CustomEvent(
                'pql:starred-changed', {detail: {items}}
            ));
        } catch (e) {}
    }

    return {
        starred: useServer
            ? false
            : readLocal().some(i => window.pqlStarKey(i) === myKey),
        count: 0,
        async init() {
            if (!useServer || !window.pqlApi) return;
            try {
                const url = `/api/social/${kind}/${encodeURI(ref)}/star`;
                const res = await window.pqlApi.fetch(url, { silent: true });
                if (res && res.ok && res.data) {
                    this.starred = !!res.data.starred;
                    this.count = res.data.count || 0;
                }
            } catch (e) {
                // Server unreachable → keep current state.
            }
        },
        async toggle() {
            if (useServer && window.pqlApi) {
                const url = `/api/social/${kind}/${encodeURI(ref)}/star`;
                const method = this.starred ? 'DELETE' : 'POST';
                try {
                    const res = await window.pqlApi.fetch(url, {
                        method, silent: true,
                    });
                    if (res && res.ok && res.data) {
                        this.starred = !!res.data.starred;
                        this.count = res.data.count || 0;
                        return;
                    }
                    // Non-200 (kind not yet registered, e.g.) → fall
                    // through to localStorage to keep the click
                    // visually responsive.
                } catch (e) {
                    // Fall through to localStorage.
                }
            }
            let items = readLocal();
            if (items.some(i => window.pqlStarKey(i) === myKey)) {
                items = items.filter(i => window.pqlStarKey(i) !== myKey);
                this.starred = false;
            } else {
                items.unshift(Object.assign({ ts: Date.now() }, payload));
                this.starred = true;
            }
            writeLocal(items);
        },
    };
};
