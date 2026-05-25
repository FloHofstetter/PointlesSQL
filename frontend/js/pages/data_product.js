/**
 * Data-product detail-page Alpine factory.
 *
 * Owns the tab-driven lazy-load state for a single data product —
 * Overview/Schema/Discussion/Reviews/Activity/Lineage/Diff/Readme —
 * plus DP-level reactions, follow state, comment threads with replies,
 * 1-5-star reviews, schema-change proposals, README edit + diff,
 * Cytoscape lineage render, and the contributor heatmap.
 *
 * Lifted from the inline ``<script>`` block in
 * ``pages/_partials/data_product/scripts.html``. ``bootstrap.js``
 * re-attaches the factory to ``window.dataProductDetail`` so the
 * existing template ``x-data='dataProductDetail({{ product|tojson }},
 * {ctx…})'`` resolves unchanged.
 */

export function dataProductDetail(product, ctx) {
  ctx = ctx || {};
  return {
    product: product,
    currentUserId: ctx.current_user_id || 0,
    isAdmin: !!ctx.is_admin,
    isSteward: !!ctx.is_steward,
    detail: null,
    diff: null,
    diffLoading: false,
    diffError: null,
    lineageLoaded: false,
    lineageEmpty: false,
    activity: [],
    activityLoaded: false,
    activityTotal: null,
    comments: [],
    commentsLoaded: false,
    commentsTotal: null,
    newCommentDraft: '',
    // category for the next top-level comment.
    newCommentCategory: 'general',
    // DP-level reactions, keyed by emoji.
    dpReactions: {},
    replyingTo: null,
    replyDraft: '',
    reviews: [],
    reviewsLoaded: false,
    reviewSummary: null,
    myReview: null,
    reviewDraftStars: 0,
    reviewDraftBody: '',
    reviewSort: 'recent',
    following: false,
    followersCount: 0,
    readme: null,
    readmeLoaded: false,
    readmeHistory: [],
    editingReadme: false,
    readmeDraft: '',
    historyOpen: false,
    diffFrom: null,
    diffTo: null,
    diffText: '',
    // auto-generated system passport.
    passport: null,
    passportLoaded: false,
    // related products from cooccurrence cache.
    related: [],
    relatedLoaded: false,
    // open schema-change proposals.
    proposals: [],
    proposalsLoaded: false,

    get canEditReadme() {
      return this.isAdmin || this.isSteward;
    },

    async init() {
      await this.loadDetail();
      await this.loadReviewSummary();
      await this.loadFollowState();
      this.loadRelated();
      this.loadProposals();
      // README on the Overview hero, eager-loaded.
      this.loadReadme();
      // Forks (active Delta branches off this DP).
      this.loadForks();
      // Contributor heatmap data.
      this.loadHeatmap();
      this.wireLazyTabs();
      this.maybeTriggerInitialTabLoad();
    },

    // derived computed surfaces -----------------------

    get healthBand() {
      const b = (this.detail && this.detail.badges) || {};
      const fresh = b.freshness_on_time_30d_pct;
      const rollbackPassed = b.last_rollback_passed;
      let status = 'unknown';
      let label = 'No telemetry yet';
      if (fresh !== null && fresh !== undefined) {
        if (fresh >= 95 && rollbackPassed !== false) {
          status = 'green';
          label = 'Healthy';
        } else if (fresh >= 75) {
          status = 'yellow';
          label = 'Degraded freshness';
        } else {
          status = 'red';
          label = 'Freshness below threshold';
        }
        if (rollbackPassed === false) {
          status = 'red';
          label = 'Last rollback failed';
        }
      }
      return {
        status,
        label,
        freshness_pct: fresh,
        downstream: b.downstream_count || 0,
        agent_runs_7d: b.agent_run_count_7d || 0,
        sla_minutes: this.product.sla_minutes,
      };
    },

    get firstSchemaTable() {
      if (!this.detail || !this.detail.tables || this.detail.tables.length === 0) {
        return null;
      }
      return this.detail.tables[0];
    },

    get schemaPreviewColumns() {
      const t = this.firstSchemaTable;
      if (!t || !t.columns) return [];
      return t.columns.slice(0, 10);
    },

    get consumeSnippets() {
      const t = this.firstSchemaTable;
      const fqn = t
        ? this.product.catalog + '.' + this.product.schema + '.' + t.name
        : this.product.catalog + '.' + this.product.schema + '.<table>';
      return {
        pql: 'from pointlessql import PQL\npql = PQL()\ndf = pql.read_table("' + fqn + '")',
        sql: 'SELECT *\nFROM ' + fqn + '\nLIMIT 100;',
        python:
          'import pandas as pd\nfrom pointlessql import PQL\ndf = pql.read_table("' +
          fqn +
          '")\nprint(df.head())',
      };
    },

    async copySnippet(kind) {
      const snip = this.consumeSnippets[kind];
      if (snip) navigator.clipboard.writeText(snip);
    },

    // forks (active branches off this DP's schema).

    forks: [],
    forksLoaded: false,
    async loadForks() {
      this.forksLoaded = false;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/forks'
        );
        if (!res.ok) {
          this.forks = [];
          return;
        }
        const data = await res.json();
        this.forks = data.forks || [];
      } catch (e) {
        console.error('forks load failed', e);
        this.forks = [];
      } finally {
        this.forksLoaded = true;
      }
    },

    // Contributor heatmap.

    heatmap: { cells: [], total: 0 },
    heatmapLoaded: false,
    async loadHeatmap() {
      this.heatmapLoaded = false;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/heatmap'
        );
        if (!res.ok) {
          this.heatmap = { cells: [], total: 0 };
          return;
        }
        this.heatmap = await res.json();
      } catch (e) {
        console.error('heatmap load failed', e);
        this.heatmap = { cells: [], total: 0 };
      } finally {
        this.heatmapLoaded = true;
      }
    },

    maybeTriggerInitialTabLoad() {
      const active = document.querySelector('.nav-link.active[data-pql-tab-key]');
      if (!active) return;
      const key = active.dataset.pqlTabKey;
      const loaders = {
        discussion: () => {
          this.loadComments();
          this.loadDpReactions();
        },
        lineage: () => this.loadLineage(),
        activity: () => this.loadActivity(),
        reviews: () => this.loadReviews(),
        diff: () => this.loadDiff(),
        readme: () => this.loadReadme(),
      };
      if (loaders[key]) loaders[key]();
    },

    get openProposals() {
      return (this.proposals || []).filter((p) => p.status === 'open');
    },

    async loadProposals() {
      this.proposalsLoaded = false;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/proposals'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.proposals = data.proposals || [];
      } catch (e) {
        console.error('proposals load failed', e);
        this.proposals = [];
      } finally {
        this.proposalsLoaded = true;
      }
    },

    async resolveProposal(p, kind) {
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/proposals/' +
            p.id +
            '/approve',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind: kind }),
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        await this.loadProposals();
      } catch (e) {
        console.error('approve failed', e);
      }
    },

    async rejectProposal(p) {
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/proposals/' +
            p.id +
            '/reject',
          {
            method: 'POST',
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        await this.loadProposals();
      } catch (e) {
        console.error('reject failed', e);
      }
    },

    async loadRelated() {
      this.relatedLoaded = false;
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/related?limit=5'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.related = data.related || [];
      } catch (e) {
        console.error('related load failed', e);
        this.related = [];
      } finally {
        this.relatedLoaded = true;
      }
    },

    async loadReadme() {
      this.readmeLoaded = false;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/readme'
        );
        if (res.status === 404) {
          this.readme = null;
        } else if (!res.ok) {
          throw new Error('HTTP ' + res.status);
        } else {
          this.readme = await res.json();
        }
        const histRes = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/readme/history'
        );
        if (histRes.ok) {
          const data = await histRes.json();
          this.readmeHistory = data.versions || [];
        }
        await this.loadPassport();
      } catch (e) {
        console.error('readme load failed', e);
      } finally {
        this.readmeLoaded = true;
      }
    },

    async loadPassport() {
      this.passportLoaded = false;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/passport'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.passport = data.latest || null;
      } catch (e) {
        console.error('passport load failed', e);
        this.passport = null;
      } finally {
        this.passportLoaded = true;
      }
    },

    async refreshPassport() {
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/passport/refresh',
          {
            method: 'POST',
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        await this.loadPassport();
      } catch (e) {
        console.error('passport refresh failed', e);
      }
    },

    startReadmeEdit() {
      this.readmeDraft = this.readme ? this.readme.body_md : '';
      this.editingReadme = true;
    },

    cancelReadmeEdit() {
      this.editingReadme = false;
      this.readmeDraft = '';
    },

    async saveReadme() {
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/readme',
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ body_md: this.readmeDraft }),
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.editingReadme = false;
        this.readmeDraft = '';
        await this.loadReadme();
      } catch (e) {
        console.error('readme save failed', e);
      }
    },

    toggleHistory() {
      this.historyOpen = !this.historyOpen;
      this.diffText = '';
    },

    async loadFollowState() {
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/followers/count'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.following = !!data.following;
        this.followersCount = data.count || 0;
      } catch (e) {
        console.error('follow state failed', e);
      }
    },

    async toggleFollow() {
      const method = this.following ? 'DELETE' : 'POST';
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/follow',
          {
            method: method,
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        await this.loadFollowState();
      } catch (e) {
        console.error('follow toggle failed', e);
      }
    },

    async loadReviewSummary() {
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reviews'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.reviewSummary = data.summary;
        this.myReview = data.my_review;
      } catch (e) {
        console.error('review summary failed', e);
      }
    },

    get sortedReviews() {
      const arr = (this.reviews || []).slice();
      if (this.reviewSort === 'stars-desc') {
        arr.sort((a, b) => b.stars - a.stars);
      } else if (this.reviewSort === 'stars-asc') {
        arr.sort((a, b) => a.stars - b.stars);
      } else {
        arr.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
      }
      return arr;
    },

    async loadReviews() {
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reviews'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.reviews = data.reviews || [];
        this.reviewSummary = data.summary;
        this.myReview = data.my_review;
        if (this.myReview) {
          this.reviewDraftStars = this.myReview.stars;
          this.reviewDraftBody = this.myReview.body_md || '';
        }
      } catch (e) {
        console.error('reviews load failed', e);
      } finally {
        this.reviewsLoaded = true;
      }
    },

    async submitReview() {
      if (this.reviewDraftStars < 1 || this.reviewDraftStars > 5) return;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reviews',
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stars: this.reviewDraftStars, body_md: this.reviewDraftBody }),
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        await this.loadReviews();
      } catch (e) {
        console.error('review post failed', e);
      }
    },

    async deleteOwnReview() {
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reviews',
          {
            method: 'DELETE',
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.reviewDraftStars = 0;
        this.reviewDraftBody = '';
        await this.loadReviews();
      } catch (e) {
        console.error('review delete failed', e);
      }
    },

    get topLevelComments() {
      return (this.comments || []).filter((c) => c.parent_comment_id === null);
    },

    repliesOf(parentId) {
      return (this.comments || []).filter((c) => c.parent_comment_id === parentId);
    },

    canDelete(c) {
      return this.isAdmin || this.isSteward || c.author.user_id === this.currentUserId;
    },

    startReply(id) {
      this.replyingTo = id;
      this.replyDraft = '';
    },

    async loadActivity() {
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/activity?limit=100'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.activity = data.activity || [];
        this.activityTotal = this.activity.length;
      } catch (e) {
        console.error('activity load failed', e);
      } finally {
        this.activityLoaded = true;
      }
    },

    async loadComments() {
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/comments'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.comments = data.comments || [];
        this.commentsTotal = this.comments.length;
      } catch (e) {
        console.error('comments load failed', e);
      } finally {
        this.commentsLoaded = true;
      }
    },

    async submitNew() {
      const body = this.newCommentDraft.trim();
      if (!body) return;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/comments',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              body_md: body,
              category: this.newCommentCategory || 'general',
            }),
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.newCommentDraft = '';
        this.newCommentCategory = 'general';
        await this.loadComments();
      } catch (e) {
        console.error('comment post failed', e);
      }
    },

    // accept-answer authz mirrors the server: steward, install-admin,
    // or the OP (top-level question author).
    canAcceptAnswer(topLevel, reply) {
      if (!topLevel || !reply) return false;
      if (topLevel.category !== 'question') return false;
      return (
        this.isAdmin ||
        this.isSteward ||
        (topLevel.author && topLevel.author.user_id === this.currentUserId)
      );
    },

    async acceptAnswer(replyId) {
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/comments/' +
            replyId +
            '/accept-answer',
          {
            method: 'POST',
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        await this.loadComments();
      } catch (e) {
        console.error('accept-answer failed', e);
      }
    },

    async toggleCommentReaction(commentId, emoji) {
      // Find the comment + emoji-row in current state; if already
      // reacted, DELETE — else POST.
      const comment = (this.comments || []).find((c) => c.id === commentId);
      const row = comment && (comment.reactions || []).find((r) => r.emoji === emoji);
      const url =
        '/api/data-products/' +
        this.product.catalog +
        '/' +
        this.product.schema +
        '/comments/' +
        commentId +
        '/reactions';
      try {
        if (row && row.has_current_user_reacted) {
          const res = await fetch(url + '/' + encodeURIComponent(emoji), { method: 'DELETE' });
          if (!res.ok) throw new Error('HTTP ' + res.status);
        } else {
          const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ emoji: emoji }),
          });
          if (!res.ok) throw new Error('HTTP ' + res.status);
        }
        await this.loadComments();
      } catch (e) {
        console.error('comment reaction toggle failed', e);
      }
    },

    async loadDpReactions() {
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reactions'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        const next = {};
        for (const r of data.reactions || []) {
          next[r.emoji] = { count: r.count, mine: r.has_current_user_reacted };
        }
        this.dpReactions = next;
      } catch (e) {
        console.error('dp reactions load failed', e);
      }
    },

    async toggleDpReaction(emoji) {
      const current = this.dpReactions[emoji];
      const url =
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reactions';
      try {
        if (current && current.mine) {
          const res = await fetch(url + '/' + encodeURIComponent(emoji), { method: 'DELETE' });
          if (!res.ok) throw new Error('HTTP ' + res.status);
        } else {
          const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ emoji: emoji }),
          });
          if (!res.ok) throw new Error('HTTP ' + res.status);
        }
        await this.loadDpReactions();
      } catch (e) {
        console.error('dp reaction toggle failed', e);
      }
    },

    async submitReply(parentId) {
      const body = this.replyDraft.trim();
      if (!body) return;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/comments',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ body_md: body, parent_comment_id: parentId }),
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.replyingTo = null;
        this.replyDraft = '';
        await this.loadComments();
      } catch (e) {
        console.error('reply post failed', e);
      }
    },

    async deleteComment(id) {
      try {
        const res = await fetch(
          '/api/data-products/' +
            this.product.catalog +
            '/' +
            this.product.schema +
            '/comments/' +
            id,
          {
            method: 'DELETE',
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        await this.loadComments();
      } catch (e) {
        console.error('comment delete failed', e);
      }
    },

    async loadDetail() {
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.detail = await res.json();
      } catch (e) {
        console.error('detail load failed', e);
      }
    },

    wireLazyTabs() {
      const diffBtn = document.querySelector('[data-bs-target="#tab-diff"]');
      if (diffBtn) {
        diffBtn.addEventListener('shown.bs.tab', () => this.loadDiff(), { once: true });
      }
      const lineageBtn = document.querySelector('[data-bs-target="#tab-lineage"]');
      if (lineageBtn) {
        lineageBtn.addEventListener('shown.bs.tab', () => this.loadLineage(), { once: true });
      }
      const discussionBtn = document.querySelector('[data-bs-target="#tab-discussion"]');
      if (discussionBtn) {
        discussionBtn.addEventListener(
          'shown.bs.tab',
          () => {
            this.loadComments();
            this.loadDpReactions();
          },
          { once: true }
        );
      }
      const activityBtn = document.querySelector('[data-bs-target="#tab-activity"]');
      if (activityBtn) {
        activityBtn.addEventListener('shown.bs.tab', () => this.loadActivity(), { once: true });
      }
      const reviewsBtn = document.querySelector('[data-bs-target="#tab-reviews"]');
      if (reviewsBtn) {
        reviewsBtn.addEventListener('shown.bs.tab', () => this.loadReviews(), { once: true });
      }
      const readmeBtn = document.querySelector('[data-bs-target="#tab-readme"]');
      if (readmeBtn) {
        readmeBtn.addEventListener('shown.bs.tab', () => this.loadReadme(), { once: true });
      }
    },

    async loadDiff() {
      this.diffLoading = true;
      this.diffError = null;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/diff'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.diff = await res.json();
      } catch (e) {
        this.diffError = 'Diff failed: ' + e.message;
      } finally {
        this.diffLoading = false;
      }
    },

    async loadLineage() {
      try {
        if (typeof window.loadCytoscapeOnce === 'function') {
          await window.loadCytoscapeOnce();
        }
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/lineage'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (!data.nodes || data.nodes.length === 0) {
          this.lineageEmpty = true;
          this.lineageLoaded = true;
          return;
        }
        this.lineageLoaded = true;
        if (typeof window.renderModelGraph === 'function') {
          window.renderModelGraph('dp-cy', data);
        } else if (typeof cytoscape === 'function') {
          cytoscape({
            container: document.getElementById('dp-cy'),
            elements: { nodes: data.nodes, edges: data.edges },
            layout: { name: 'breadthfirst' },
            style: [
              { selector: 'node', style: { label: 'data(label)', 'background-color': '#0d6efd' } },
              {
                selector: 'edge',
                style: { 'curve-style': 'bezier', 'target-arrow-shape': 'triangle' },
              },
            ],
          });
        }
      } catch (e) {
        console.error('lineage load failed', e);
        this.lineageEmpty = true;
        this.lineageLoaded = true;
      }
    },
  };
}
