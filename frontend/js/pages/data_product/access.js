/**
 * Data-product detail page — Self-service access requests on the Data tab.
 *
 * One slice of the ``dataProductDetail`` Alpine factory.  ``installDpAccess``
 * mutates the shared component object in place (the project's mixin-installer
 * pattern); ``this`` resolves to the live component at call time, so the
 * method bodies are unchanged from the original single-file factory.
 */

export function installDpAccess(state) {
  Object.assign(state, {

    // --- Self-service access (Data tab) ----------------

    _accessBase() {
      return '/api/data-products/' + this.product.catalog + '/' + this.product.schema;
    },

    async loadAccessStatus() {
      try {
        const res = await fetch(this._accessBase() + '/access-requests/status');
        if (!res.ok) return;
        this.accessStatus = await res.json();
        if (this.accessStatus.is_steward) this.loadAccessRequests();
      } catch (_e) {
        /* swallow — access affordance is best-effort */
      }
    },

    async loadAccessRequests() {
      try {
        const res = await fetch(this._accessBase() + '/access-requests');
        if (!res.ok) return;
        const data = await res.json();
        this.accessRequests = Array.isArray(data.requests) ? data.requests : [];
      } catch (_e) {
        /* swallow */
      }
    },

    async requestAccess() {
      if (this.accessBusy) return;
      this.accessBusy = true;
      try {
        const res = await fetch(this._accessBase() + '/access-requests', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ note: this.accessNote || null }),
        });
        if (res.ok) {
          this.accessNote = '';
          await this.loadAccessStatus();
          window.pqlToast?.success?.('Access requested — a steward will review it.');
        } else {
          const b = await res.json().catch(() => ({}));
          window.pqlToast?.error?.(b.detail || 'Could not file the request.');
        }
      } finally {
        this.accessBusy = false;
      }
    },

    async approveAccess(id) {
      if (this.accessBusy) return;
      this.accessBusy = true;
      try {
        const res = await fetch(this._accessBase() + '/access-requests/' + id + '/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        if (res.ok) {
          const d = await res.json().catch(() => ({}));
          const msg =
            d.failed && d.failed.length
              ? 'Approved, but some table grants were rejected — check with an admin.'
              : 'Approved and access granted.';
          window.pqlToast?.success?.(msg);
          await this.loadAccessRequests();
        } else {
          window.pqlToast?.error?.('Could not approve the request.');
        }
      } finally {
        this.accessBusy = false;
      }
    },

    async denyAccess(id) {
      if (this.accessBusy) return;
      this.accessBusy = true;
      try {
        const res = await fetch(this._accessBase() + '/access-requests/' + id + '/deny', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        if (res.ok) {
          window.pqlToast?.success?.('Request denied.');
          await this.loadAccessRequests();
        } else {
          window.pqlToast?.error?.('Could not deny the request.');
        }
      } finally {
        this.accessBusy = false;
      }
    }
  });
}
