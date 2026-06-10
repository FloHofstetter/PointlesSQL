/**
 * Data-product detail page — README + passport, related products, and schema-change proposals.
 *
 * One slice of the ``dataProductDetail`` Alpine factory.  ``installDpContent``
 * mutates the shared component object in place (the project's mixin-installer
 * pattern); ``this`` resolves to the live component at call time, so the
 * method bodies are unchanged from the original single-file factory.
 */

export function installDpContent(state) {
  Object.assign(state, {
    async loadProposals() {
      this.proposalsLoaded = false;
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/proposals',
        { silent: true }
      );
      if (!res.ok) {
        console.error('proposals load failed', new Error('HTTP ' + res.status));
        this.proposals = [];
        this.proposalsLoaded = true;
        return;
      }
      this.proposals = (res.data && res.data.proposals) || [];
      this.proposalsLoaded = true;
    },

    async resolveProposal(p, kind) {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/proposals/' +
          p.id +
          '/approve',
        {
          method: 'POST',
          body: { kind: kind },
          silent: true,
        }
      );
      if (!res.ok) {
        console.error('approve failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadProposals();
    },

    async rejectProposal(p) {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/proposals/' +
          p.id +
          '/reject',
        { method: 'POST', silent: true }
      );
      if (!res.ok) {
        console.error('reject failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadProposals();
    },

    async loadRelated() {
      this.relatedLoaded = false;
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/related?limit=5',
        { silent: true }
      );
      if (!res.ok) {
        console.error('related load failed', new Error('HTTP ' + res.status));
        this.related = [];
        this.relatedLoaded = true;
        return;
      }
      this.related = (res.data && res.data.related) || [];
      this.relatedLoaded = true;
    },

    async loadReadme() {
      this.readmeLoaded = false;
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/readme',
        { silent: true }
      );
      if (res.status === 404) {
        this.readme = null;
      } else if (!res.ok) {
        console.error('readme load failed', new Error('HTTP ' + res.status));
        this.readmeLoaded = true;
        return;
      } else {
        this.readme = res.data;
      }
      const histRes = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/readme/history',
        { silent: true }
      );
      if (histRes.status === 0) {
        console.error('readme load failed', new Error('HTTP ' + histRes.status));
        this.readmeLoaded = true;
        return;
      }
      if (histRes.ok) {
        this.readmeHistory = (histRes.data && histRes.data.versions) || [];
      }
      await this.loadPassport();
      this.readmeLoaded = true;
    },

    async loadPassport() {
      this.passportLoaded = false;
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/passport',
        { silent: true }
      );
      if (!res.ok) {
        console.error('passport load failed', new Error('HTTP ' + res.status));
        this.passport = null;
        this.passportLoaded = true;
        return;
      }
      this.passport = (res.data && res.data.latest) || null;
      this.passportLoaded = true;
    },

    async refreshPassport() {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/passport/refresh',
        { method: 'POST', silent: true }
      );
      if (!res.ok) {
        console.error('passport refresh failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadPassport();
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
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/readme',
        {
          method: 'PUT',
          body: { body_md: this.readmeDraft },
          silent: true,
        }
      );
      if (!res.ok) {
        console.error('readme save failed', new Error('HTTP ' + res.status));
        return;
      }
      this.editingReadme = false;
      this.readmeDraft = '';
      await this.loadReadme();
    },

    toggleHistory() {
      this.historyOpen = !this.historyOpen;
      this.diffText = '';
    },
  });
}
