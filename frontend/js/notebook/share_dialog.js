/**
 * Publish / Share dialog.
 *
 * Backend (REST + public viewer + 8 tests) shipped earlier; this
 * module wires the toolbar "Share" button to a Bootstrap modal with
 * the create-share form + a list of existing shares.
 *
 * Mutates ``state`` in place per the install-pattern used by the
 * other notebook editor modules.  Field updates happen one-at-a-time
 * (no object replacement) per ``feedback_alpine_nested_object_replace``;
 * modal visibility rides ``:class="{ 'show d-block': flag }"`` per
 * ``feedback_bootstrap_modal_x_show``.
 */

export function installShareDialog(state) {
  state.shareDialog = {
    open: false,
    mode: 'snapshot',
    dashboard: false,
    message: '',
    shares: [],
    loaded: false,
    loading: false,
    submitting: false,
    error: '',
    copiedUuid: '',
  };

  /**
   * Open the modal (lazy-loads existing shares on first open).
   */
  state.openShareDialog = async function () {
    this.shareDialog.open = true;
    this.shareDialog.error = '';
    if (!this.shareDialog.loaded) {
      await this.loadShares();
    }
  };

  /**
   * Close the modal and reset the form state.
   */
  state.closeShareDialog = function () {
    this.shareDialog.open = false;
    this.shareDialog.submitting = false;
    this.shareDialog.error = '';
    this.shareDialog.copiedUuid = '';
  };

  /**
   * Fetch ``{shares: [...]}`` for this notebook path.
   */
  state.loadShares = async function () {
    if (!this.path) return;
    this.shareDialog.loading = true;
    this.shareDialog.error = '';
    try {
      const res = await window.pqlApi.fetch(
        `/api/notebooks/shares?path=${encodeURIComponent(this.path)}`,
        { silent: true }
      );
      if (res.ok && res.data) {
        this.shareDialog.shares = res.data.shares || [];
        this.shareDialog.loaded = true;
      } else {
        this.shareDialog.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
      }
    } catch (err) {
      this.shareDialog.error = (err && err.message) || String(err);
    } finally {
      this.shareDialog.loading = false;
    }
  };

  /**
   * POST a new share — server mints the UUID + revision (snapshot) and
   * we refresh the list to show the new row.
   */
  state.createShare = async function () {
    if (this.shareDialog.submitting) return;
    this.shareDialog.submitting = true;
    this.shareDialog.error = '';
    try {
      const body = {
        path: this.path,
        share_mode: this.shareDialog.mode,
        dashboard_mode: this.shareDialog.dashboard,
      };
      if (this.shareDialog.message) {
        body.message = this.shareDialog.message;
      }
      const res = await window.pqlApi.fetch('/api/notebooks/shares', {
        method: 'POST',
        body,
      });
      if (!res.ok) {
        this.shareDialog.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
        return;
      }
      this.shareDialog.message = '';
      await this.loadShares();
    } catch (err) {
      this.shareDialog.error = (err && err.message) || String(err);
    } finally {
      this.shareDialog.submitting = false;
    }
  };

  /**
   * Soft-revoke a share; the row stays in the list as a revoked
   * history entry (with ``active: false``).
   */
  state.revokeShare = async function (shareUuid) {
    if (!shareUuid) return;
    this.shareDialog.error = '';
    try {
      const res = await window.pqlApi.fetch(
        `/api/notebooks/shares/${encodeURIComponent(shareUuid)}`,
        { method: 'DELETE' }
      );
      if (!res.ok) {
        this.shareDialog.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
        return;
      }
      await this.loadShares();
    } catch (err) {
      this.shareDialog.error = (err && err.message) || String(err);
    }
  };

  /**
   * Toggle dashboard-mode on an existing share via PATCH.
   */
  state.toggleShareDashboard = async function (share) {
    if (!share || !share.share_uuid) return;
    try {
      const res = await window.pqlApi.fetch(
        `/api/notebooks/shares/${encodeURIComponent(share.share_uuid)}`,
        {
          method: 'PATCH',
          body: { dashboard_mode: !share.dashboard_mode },
        }
      );
      if (!res.ok) {
        this.shareDialog.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
        return;
      }
      await this.loadShares();
    } catch (err) {
      this.shareDialog.error = (err && err.message) || String(err);
    }
  };

  /**
   * Build the absolute URL for the share row + copy it to the clipboard.
   *
   * Uses ``navigator.clipboard.writeText`` with a textarea fallback for
   * browsers without the async clipboard API (mostly Firefox on
   * file:// pages — irrelevant here, but keeps the code defensive).
   */
  state.copyShareUrl = async function (shareUuid) {
    if (!shareUuid) return;
    const absolute = `${window.location.origin}/share/notebook/${shareUuid}`;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(absolute);
      } else {
        const ta = document.createElement('textarea');
        ta.value = absolute;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      this.shareDialog.copiedUuid = shareUuid;
      setTimeout(() => {
        if (this.shareDialog.copiedUuid === shareUuid) {
          this.shareDialog.copiedUuid = '';
        }
      }, 1800);
    } catch (err) {
      this.shareDialog.error = (err && err.message) || String(err);
    }
  };
}
