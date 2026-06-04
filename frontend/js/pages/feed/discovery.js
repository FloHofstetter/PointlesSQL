/**
 * Feed page — Trending / people sidebars and localStorage saved-searches.
 *
 * One slice of the ``feedPage`` Alpine factory.  ``installFeedDiscovery`` mutates
 * the shared component object in place (the project's mixin-installer
 * pattern, mirroring ``installFeedSocial``); ``this`` resolves to the live
 * component at call time, so the method bodies are unchanged from the
 * original single-file factory.
 */

export function installFeedDiscovery(state) {
  Object.assign(state, {

    async loadTrending() {
      try {
        const res = await fetch('/api/feed/trending');
        if (!res.ok) return;
        const data = await res.json();
        this.trending = data.rows || [];
      } catch (e) {
        /* silent — the empty-state copy covers it */
      }
    },

    async loadPeople() {
      try {
        const res = await fetch('/api/feed/people');
        if (!res.ok) return;
        const data = await res.json();
        this.people = (data.rows || []).map((p) => ({ ...p, _following: false }));
      } catch (e) {
        /* silent */
      }
    },

    async followUser(p) {
      if (p._following) return;
      try {
        const res = await fetch('/api/users/' + p.id + '/follow', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok && res.status !== 409) throw new Error('HTTP ' + res.status);
        p._following = true;
        window.pqlToast?.success?.('Following ' + p.display_name + '.');
      } catch (e) {
        console.error('followUser failed', e);
        window.pqlToast?.error?.('Could not follow user.');
      }
    },

    // Saved-searches: localStorage-backed bookmarked filter combos.
    _restoreSavedSearches() {
      try {
        const raw = window.localStorage?.getItem('pql.feed.savedSearches');
        if (raw) this.savedSearches = JSON.parse(raw) || [];
      } catch (e) {
        /* ignore */
      }
    },

    _persistSavedSearches() {
      try {
        window.localStorage?.setItem('pql.feed.savedSearches', JSON.stringify(this.savedSearches));
      } catch (e) {
        /* ignore */
      }
    },

    saveCurrentSearch() {
      const parts = [];
      if (this.filter && this.filter !== 'all') parts.push(this.filter);
      if (this.kindFilter.length > 0) parts.push(this.kindFilter.join('+'));
      if (this.searchDraft.trim()) parts.push('"' + this.searchDraft.trim() + '"');
      const label = parts.length === 0 ? 'All activity' : parts.join(' · ');
      const entry = {
        id: Date.now().toString(36),
        label,
        filter: this.filter,
        kindFilter: this.kindFilter.slice(),
        q: this.searchDraft.trim(),
      };
      this.savedSearches.push(entry);
      this._persistSavedSearches();
      window.pqlToast?.success?.('Saved search "' + label + '".');
    },

    applySavedSearch(s) {
      this.filter = s.filter || 'all';
      this.kindFilter = (s.kindFilter || []).slice();
      this.searchDraft = s.q || '';
      this.reload();
    },

    deleteSavedSearch(idx) {
      this.savedSearches.splice(idx, 1);
      this._persistSavedSearches();
    }
  });
}
