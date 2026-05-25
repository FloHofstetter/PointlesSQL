// Polymorphic discussion + README factories for the notebook editor
// right-drawer.  Two siblings:
//
//   notebookDiscussion(uuid)  comments thread under the notebook
//   notebookReadme(uuid)      README rendered + editable inline
//
// Both ride the polymorphic /api/social/notebook/{uuid}/{comments|readme}
// surface.  The drawer auto-opens on page mount, so a missing thread /
// missing README is the normal first-visit shape — both factories pass
// ``silent: true`` to suppress toast spam.

export function notebookDiscussion(notebookUuid) {
  return {
    notebookUuid: notebookUuid,
    comments: [],
    commentsLoaded: false,
    draftBody: '',
    async init() {
      const res = await window.pqlApi.fetch('/api/social/notebook/' + notebookUuid + '/comments', {
        silent: true,
      });
      this.comments = (res && res.ok && res.data && res.data.comments) || [];
      this.commentsLoaded = true;
    },
    async submitNew() {
      if (!this.draftBody.trim()) return;
      const res = await window.pqlApi.fetch('/api/social/notebook/' + notebookUuid + '/comments', {
        method: 'POST',
        body: JSON.stringify({ body_md: this.draftBody }),
      });
      if (res && res.ok) {
        this.draftBody = '';
        await this.init();
      }
    },
  };
}

export function notebookReadme(notebookUuid) {
  return {
    notebookUuid: notebookUuid,
    bodyRendered: '',
    draftBody: '',
    editing: false,
    readmeLoaded: false,
    async init() {
      const res = await window.pqlApi.fetch('/api/social/notebook/' + notebookUuid + '/readme', {
        silent: true,
      });
      this.bodyRendered =
        (res && res.ok && res.data && (res.data.body_md_resolved || res.data.body_md)) || '';
      this.draftBody = (res && res.ok && res.data && res.data.body_md) || '';
      this.readmeLoaded = true;
    },
    async save() {
      const res = await window.pqlApi.fetch(
        '/api/social/notebook/' + this.notebookUuid + '/readme',
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
