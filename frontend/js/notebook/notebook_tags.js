/**
 * Notebook-level tags.
 *
 * Wires the existing ``GET/POST/DELETE /api/notebooks/tags`` REST
 * surface to a toolbar button + inline picker panel.  Backend
 * (migration ``b185acda50d7``, service + 13 tests) shipped in Phase
 * 98.B; only the editor wiring was deferred.
 *
 * Pattern matches ``./jobs_orchestration.js`` etc. — fields + methods
 * are mixed onto the notebookEditor() state object before Alpine sees
 * it, so templates can call ``toggleTagsPicker()`` / read
 * ``notebookTags`` directly from the outer x-data scope.
 */

export function installNotebookTags(state) {
 state.tagsPickerOpen = false;
 state.notebookTags = [];
 state.notebookTagsCurated = [];
 state.notebookTagsLoaded = false;
 state.notebookTagsLoading = false;
 state.notebookTagsError = '';
 state.notebookTagsCustomMode = false;
 state.notebookTagsCustomDraft = '';

 /**
  * Open the picker (lazy-loads the tag list on first open).
  */
 state.toggleTagsPicker = async function () {
  this.tagsPickerOpen = !this.tagsPickerOpen;
  if (this.tagsPickerOpen && !this.notebookTagsLoaded) {
   await this.loadNotebookTags();
  }
 };

 /**
  * Fetch ``{tags, curated}`` for the current notebook path.
  *
  * Curated vocabulary mirrors ``CURATED_NOTEBOOK_TAGS`` in
  * ``pointlessql/services/notebook/tags.py``; the server is the
  * source of truth so a future vocab edit doesn't need a client
  * release.
  */
 state.loadNotebookTags = async function () {
  if (!this.path) return;
  this.notebookTagsLoading = true;
  this.notebookTagsError = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/tags?path=${encodeURIComponent(this.path)}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.notebookTags = res.data.tags || [];
    this.notebookTagsCurated = res.data.curated || [];
    this.notebookTagsLoaded = true;
   } else {
    this.notebookTagsError =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.notebookTagsError = (err && err.message) || String(err);
  } finally {
   this.notebookTagsLoading = false;
  }
 };

 /**
  * Add a tag (curated chip or custom input).  Server normalises
  * casing + strips a leading ``#``; the local list is replaced from
  * the fresh GET so client + server stay in sync.
  */
 state.addNotebookTag = async function (raw) {
  const tag = String(raw || '').trim().replace(/^#+/, '').trim();
  if (!tag) return;
  if (this.notebookTags.some((t) => t.tag === tag)) return;
  this.notebookTagsError = '';
  try {
   const res = await window.pqlApi.fetch('/api/notebooks/tags', {
    method: 'POST',
    body: { path: this.path, tag },
   });
   if (!res.ok) {
    this.notebookTagsError =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   await this.loadNotebookTags();
  } catch (err) {
   this.notebookTagsError = (err && err.message) || String(err);
  }
 };

 /**
  * Remove a tag.  Idempotent — a 200 with ``removed=false`` is a
  * no-op and doesn't surface as an error.
  */
 state.removeNotebookTag = async function (tag) {
  if (!tag) return;
  this.notebookTagsError = '';
  try {
   const res = await window.pqlApi.fetch('/api/notebooks/tags', {
    method: 'DELETE',
    body: { path: this.path, tag },
   });
   if (!res.ok) {
    this.notebookTagsError =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   this.notebookTags = this.notebookTags.filter((t) => t.tag !== tag);
  } catch (err) {
   this.notebookTagsError = (err && err.message) || String(err);
  }
 };

 /**
  * Submit + clear the custom-tag draft.  Called from the picker's
  * inline form; isolated here so the template stays declarative.
  */
 state.submitCustomNotebookTag = async function () {
  const draft = (this.notebookTagsCustomDraft || '').trim();
  if (!draft) return;
  await this.addNotebookTag(draft);
  this.notebookTagsCustomDraft = '';
  this.notebookTagsCustomMode = false;
 };
}
