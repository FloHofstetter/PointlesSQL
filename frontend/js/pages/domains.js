// Domain browse page (/domains).
//
// Single ``domainsBrowse`` factory: loads /api/domains and offers a
// client-side text filter + archetype-chip filter.

export function domainsBrowse() {
  return {
    domains: [],
    filter: '',
    activeArchetype: 'all',
    loading: false,
    error: null,

    async init() {
      await this.reload();
    },

    async reload() {
      this.loading = true;
      this.error = null;
      try {
        const res = await fetch('/api/domains');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.domains = Array.isArray(data.domains) ? data.domains : [];
      } catch (e) {
        this.error = 'Failed to load domains: ' + e.message;
      } finally {
        this.loading = false;
      }
    },

    get filtered() {
      const needle = this.filter.trim().toLowerCase();
      return this.domains.filter((d) => {
        if (this.activeArchetype !== 'all' && d.archetype !== this.activeArchetype) return false;
        if (!needle) return true;
        return (
          (d.name || '').toLowerCase().includes(needle) ||
          (d.slug || '').toLowerCase().includes(needle) ||
          (d.description || '').toLowerCase().includes(needle)
        );
      });
    },

    ownerLabel(d) {
      const owners = d.owners || [];
      if (owners.length === 0) return 'No owner';
      const first = owners[0].display_name || owners[0].email;
      return owners.length === 1 ? first : first + ' +' + (owners.length - 1);
    },
  };
}
