// Auto-extracted from frontend/templates/pages/schemas.html.
// Exports: catalogDiscussion, catalogReadme.
//
export function catalogDiscussion(catalogName) {
  return {
    catalogName: catalogName,
    comments: [],
    commentsLoaded: false,
    draftBody: '',
    postBusy: false,
    async init() {
      const res = await window.pqlApi.fetch(
        '/api/social/catalog/' + encodeURIComponent(catalogName) + '/comments'
      );
      this.comments = (res && res.ok && res.data && res.data.comments) || [];
      this.commentsLoaded = true;
    },
    async submitNew() {
      if (this.postBusy || !this.draftBody.trim()) return;
      this.postBusy = true;
      try {
        const res = await window.pqlApi.fetch(
          '/api/social/catalog/' + encodeURIComponent(catalogName) + '/comments',
          {
            method: 'POST',
            body: JSON.stringify({ body_md: this.draftBody }),
          }
        );
        if (res && res.ok) {
          this.draftBody = '';
          await this.init();
        }
      } finally {
        this.postBusy = false;
      }
    },
  };
}
export function catalogReadme(catalogName) {
  return {
    catalogName: catalogName,
    bodyRendered: '',
    draftBody: '',
    editing: false,
    readmeLoaded: false,
    async init() {
      const res = await window.pqlApi.fetch(
        '/api/social/catalog/' + encodeURIComponent(catalogName) + '/readme',
        { silent: true }
      );
      this.bodyRendered =
        (res && res.ok && res.data && (res.data.body_md_resolved || res.data.body_md)) || '';
      this.draftBody = (res && res.ok && res.data && res.data.body_md) || '';
      this.readmeLoaded = true;
    },
    startEdit() {
      this.editing = true;
    },
    async save() {
      const res = await window.pqlApi.fetch(
        '/api/social/catalog/' + encodeURIComponent(catalogName) + '/readme',
        {
          method: 'PUT',
          body: JSON.stringify({ body_md: this.draftBody }),
        }
      );
      if (res && res.ok) {
        this.editing = false;
        await this.init();
      }
    },
  };
}
