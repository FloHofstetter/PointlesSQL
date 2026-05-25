/**
 * Model detail-page Alpine factories.
 *
 * Six factories that back the model-detail page surfaces:
 *  - ``modelVersions(fullName)`` — version-compare two-click selector
 *  - ``modelPromotion(fullName, initialChampion)`` — champion-version
 *    promotion modal + history
 *  - ``modelDiscussion(ref)`` — per-model comment thread
 *  - ``modelReadme(ref)`` — per-model README with edit + render
 *  - ``modelReviews(ref)`` — 1-5-star review aggregation + submit
 *  - ``modelLineageDag(fullName)`` — Cytoscape lineage DAG on the
 *    Lineage tab
 *
 * Lifted from the inline ``<script>`` block in ``pages/model.html``.
 * Bootstrap.js re-attaches every factory to ``window.*`` so the
 * existing partial templates' ``x-data='modelDiscussion({{ ref }})'``
 * etc. resolve unchanged. The one Jinja-coupled site
 * (``modelVersions()`` previously rendered ``{{ model.full_name }}``
 * inside the JS body) now takes ``fullName`` as a constructor arg —
 * the template was updated accordingly.
 */

export function modelVersions(fullName) {
 return {
  firstSelected: null,
  selectForCompare(version) {
   if (this.firstSelected === null) {
    this.firstSelected = version;
    return;
   }
   if (this.firstSelected === version) {
    this.firstSelected = null;
    return;
   }
   const url = '/models/' + fullName + '/compare?v1=' + this.firstSelected + '&v2=' + version;
   window.location.href = url;
  },
 };
}

export function modelPromotion(fullName, initialChampion) {
 return {
  champion: initialChampion === null || initialChampion === undefined ? null : initialChampion,
  history: [],
  latestPromotion: null,
  targetVersion: null,
  reason: '',
  busy: false,
  error: null,
  modal: null,

  async init() {
   this.modal = new bootstrap.Modal(document.getElementById('promote-modal'));
   await this.refresh();
  },

  async refresh() {
   try {
    const res = await fetch('/api/models/' + encodeURIComponent(fullName) + '/promotion');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    this.champion = data.champion_version;
    this.history = data.history || [];
    this.latestPromotion = this.history.length > 0 ? this.history[0] : null;
   } catch (e) {
    console.error('promotion refresh failed', e);
   }
  },

  openPromoteModal(version) {
   this.targetVersion = version;
   this.reason = '';
   this.error = null;
   this.modal.show();
  },

  async submit() {
   if (!this.reason.trim()) return;
   this.busy = true;
   this.error = null;
   try {
    const res = await fetch('/api/models/' + encodeURIComponent(fullName) + '/promote', {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
      target_version: this.targetVersion,
      reason: this.reason.trim(),
     }),
    });
    if (!res.ok) {
     const detail = await res.json().catch(() => ({}));
     throw new Error(detail.detail || ('HTTP ' + res.status));
    }
    this.modal.hide();
    await this.refresh();
   } catch (e) {
    this.error = e.message;
   } finally {
    this.busy = false;
   }
  },
 };
}

// per-tab Alpine factories for the inline Discussion + README + Reviews
// panes on model.html. Endorsements + Followers panes reuse the
// kind-agnostic socialTabs factory + the polymorphic partials; these
// three stay model-specific because the existing partials are
// data_product.html-coupled (deferred unification).

export function modelDiscussion(ref) {
 const url = '/api/social/model/' + encodeURI(ref) + '/comments';
 return {
  ref,
  commentsLoaded: false,
  comments: [],
  draftBody: '',
  postBusy: false,

  async init() {
   await this.loadComments();
  },

  async loadComments() {
   const res = await window.pqlApi.fetch(url, { silent: true });
   if (!res.ok) {
    this.commentsLoaded = true;
    return;
   }
   this.comments = (res.data && res.data.comments) || [];
   this.commentsLoaded = true;
  },

  async submitNew() {
   const body = this.draftBody.trim();
   if (!body || this.postBusy) return;
   this.postBusy = true;
   try {
    const res = await window.pqlApi.fetch(url, {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ body_md: body }),
    });
    if (!res.ok) {
     if (window.pqlToast) window.pqlToast.error('Comment failed to post.');
     return;
    }
    this.draftBody = '';
    await this.loadComments();
   } finally {
    this.postBusy = false;
   }
  },

  async deleteComment(commentId) {
   if (!window.confirm('Soft-delete this comment?')) return;
   const res = await window.pqlApi.fetch(url + '/' + commentId, {
    method: 'DELETE',
   });
   if (!res.ok) {
    if (window.pqlToast) window.pqlToast.error('Delete failed.');
    return;
   }
   await this.loadComments();
  },
 };
}

export function modelReadme(ref) {
 const url = '/api/social/model/' + encodeURI(ref) + '/readme';
 return {
  ref,
  readmeLoaded: false,
  body: '',
  draftBody: '',
  editing: false,
  saveBusy: false,

  get renderedBody() {
   if (window.pqlMarkdown && window.pqlMarkdown.render) {
    return window.pqlMarkdown.render(this.body || '');
   }
   return '<pre class="small">' + this._escape(this.body || '') + '</pre>';
  },

  _escape(s) {
   return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  },

  async init() {
   const res = await window.pqlApi.fetch(url, { silent: true });
   if (res.ok && res.data) {
    this.body = res.data.body_md || '';
   }
   this.readmeLoaded = true;
  },

  startEdit() {
   this.draftBody = this.body;
   this.editing = true;
  },

  cancelEdit() {
   this.draftBody = '';
   this.editing = false;
  },

  async save() {
   if (this.saveBusy) return;
   this.saveBusy = true;
   try {
    const res = await window.pqlApi.fetch(url, {
     method: 'PUT',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ body_md: this.draftBody }),
     silent: true,
    });
    if (!res.ok) {
     if (window.pqlToast) {
      window.pqlToast.error(
       res.status === 403
        ? 'README edit is admin-only on models for now.'
        : 'Save failed.',
      );
     }
     return;
    }
    this.body = (res.data && res.data.body_md) || this.draftBody;
    this.editing = false;
   } finally {
    this.saveBusy = false;
   }
  },
 };
}

export function modelReviews(ref) {
 const url = '/api/social/model/' + encodeURI(ref) + '/reviews';
 return {
  ref,
  reviewsLoaded: false,
  reviews: [],
  summary: { avg_stars: null, count: 0 },
  myReview: null,
  draftStars: 0,
  draftBody: '',
  postBusy: false,

  async init() {
   await this.load();
  },

  async load() {
   const res = await window.pqlApi.fetch(url, { silent: true });
   if (!res.ok) {
    this.reviewsLoaded = true;
    return;
   }
   const data = res.data || {};
   this.reviews = data.reviews || [];
   this.summary = data.summary || { avg_stars: null, count: 0 };
   this.myReview = data.my_review || null;
   if (this.myReview) {
    this.draftStars = this.myReview.stars;
    this.draftBody = this.myReview.body_md || '';
   }
   this.reviewsLoaded = true;
  },

  async submitMine() {
   if (this.postBusy || this.draftStars < 1) return;
   this.postBusy = true;
   try {
    const res = await window.pqlApi.fetch(url, {
     method: 'PUT',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
      stars: this.draftStars,
      body_md: this.draftBody,
     }),
    });
    if (!res.ok) {
     if (window.pqlToast) window.pqlToast.error('Review save failed.');
     return;
    }
    await this.load();
   } finally {
    this.postBusy = false;
   }
  },

  async deleteMine() {
   if (!this.myReview) return;
   if (!window.confirm('Remove your review?')) return;
   const res = await window.pqlApi.fetch(url, { method: 'DELETE' });
   if (!res.ok) {
    if (window.pqlToast) window.pqlToast.error('Delete failed.');
    return;
   }
   this.draftStars = 0;
   this.draftBody = '';
   await this.load();
  },
 };
}

export function modelLineageDag(fullName) {
 return {
  loaded: false,
  loading: false,
  error: null,
  empty: false,
  predictions: [],
  _started: false,

  init() {
   // Lazy: only fetch when the Lineage tab is actually shown.
   const btn = document.querySelector('[data-bs-target="#tab-lineage"]');
   if (btn) {
    btn.addEventListener('shown.bs.tab', () => this.render(), { once: true });
   }
  },

  async render() {
   if (this._started) return;
   this._started = true;
   this.loading = true;
   this.error = null;
   try {
    if (typeof loadCytoscapeOnce === 'function') {
     await loadCytoscapeOnce();
    }
    const [graphRes, predsRes] = await Promise.all([
     fetch('/api/models/' + encodeURIComponent(fullName) + '/lineage'),
     fetch('/api/models/' + encodeURIComponent(fullName) + '/predictions'),
    ]);
    if (!graphRes.ok) throw new Error('HTTP ' + graphRes.status);
    const data = await graphRes.json();
    if (predsRes.ok) {
     const predsData = await predsRes.json();
     this.predictions = predsData.predictions || [];
    }
    if (!data.nodes || data.nodes.length <= 1) {
     this.empty = true;
     this.loaded = true;
     return;
    }
    if (typeof window.renderModelGraph === 'function') {
     window.renderModelGraph('model-cy', data);
    }
    this.loaded = true;
   } catch (e) {
    this.error = 'Failed to load lineage: ' + e.message;
    this._started = false;
   } finally {
    this.loading = false;
   }
  },

  async reload() {
   this._started = false;
   this.loaded = false;
   this.empty = false;
   this.predictions = [];
   await this.render();
  },
 };
}
