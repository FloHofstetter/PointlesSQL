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
  });
}
