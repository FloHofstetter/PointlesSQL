// Workspace library — pinned-facts browse page (Phase 97 Rest UI).
//
// Mounts on the ``/library/facts`` template via ``x-data="factsLibrary()"``.
// Loads ``GET /api/notebooks/facts`` with optional ``include_unpinned``
// flag, renders fact cards, supports a client-side text filter and an
// "Unpin" action per card.

export function factsLibrary() {
 return {
  facts: [],
  loading: false,
  error: '',
  query: '',
  includeUnpinned: false,

  async load() {
   this.loading = true;
   this.error = '';
   try {
    const qs = new URLSearchParams({ limit: '200' });
    if (this.includeUnpinned) qs.set('include_unpinned', 'true');
    const res = await window.pqlApi.fetch(
     `/api/notebooks/facts?${qs.toString()}`,
     { silent: true },
    );
    if (res.ok && res.data) {
     this.facts = res.data.facts || [];
    } else {
     this.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
    }
   } catch (err) {
    this.error = (err && err.message) || String(err);
   } finally {
    this.loading = false;
   }
  },

  filtered() {
   const q = (this.query || '').trim().toLowerCase();
   if (!q) return this.facts;
   return this.facts.filter((f) => {
    const title = (f.title || '').toLowerCase();
    const desc = (f.description_md || '').toLowerCase();
    return title.includes(q) || desc.includes(q);
   });
  },

  async unpin(factUuid) {
   if (!factUuid) return;
   try {
    const res = await window.pqlApi.fetch(
     `/api/notebooks/facts/${encodeURIComponent(factUuid)}`,
     { method: 'DELETE' },
    );
    if (!res.ok) {
     this.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
     return;
    }
    await this.load();
   } catch (err) {
    this.error = (err && err.message) || String(err);
   }
  },
 };
}
