/**
 * Data-product detail page — init, tab wiring, and the base detail fetch.
 *
 * One slice of the ``dataProductDetail`` Alpine factory.  ``installDpLifecycle``
 * mutates the shared component object in place (the project's mixin-installer
 * pattern); ``this`` resolves to the live component at call time, so the
 * method bodies are unchanged from the original single-file factory.
 */

export function installDpLifecycle(state) {
  Object.assign(state, {

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
      // Self-service access posture for the Data tab.
      this.loadAccessStatus();
      this.wireLazyTabs();
      this.maybeTriggerInitialTabLoad();
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
        ask: () => this.openAsk(),
      };
      if (loaders[key]) loaders[key]();
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
      const askBtn = document.querySelector('[data-bs-target="#tab-ask"]');
      if (askBtn) {
        askBtn.addEventListener('shown.bs.tab', () => this.openAsk(), { once: true });
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
    }
  });
}
