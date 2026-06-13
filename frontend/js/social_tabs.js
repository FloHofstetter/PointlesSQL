/*
 * PointlesSQL polymorphic social-tabs Alpine factory.
 *
 * Backs the kind-agnostic ``_endorsements_pane.html`` +
 * ``_followers_pane.html`` partials when they are included from a
 * table.html or branch_detail.html tab strip.  The factory wraps every
 * social write in a ``/api/social/{kind}/{ref}/...`` call so the
 * polymorphic backend handlers (``_polymorphic_handlers.py``) are
 * exercised.
 *
 * Mount on the parent ``<div>`` like:
 *
 *     <div x-data="socialTabs({ kind: 'table', ref: '{{ catalog }}.{{ schema }}.{{ table_name }}' })">
 *       {% include 'partials/social/_endorsements_pane.html' %}
 *       {% include 'partials/social/_followers_pane.html' %}
 *     </div>
 *
 * Decisions baked in here:
 *
 * * Follow / unfollow returns 501 on non-DP kinds today.  The factory
 *   surfaces that to the partial as ``followLocked: true`` so the
 *   button can render disabled with a hint instead of fetching the
 *   error and swallowing it.
 * * Endorsement types are sourced from ``params.endorsementTypes``
 *   (an array of ``{key, label}`` records the parent page picks based
 *   on entity-kind).  The factory has no opinion about which types
 *   apply to which kind — the registry / parent template decides.
 * * ``data_product.html`` keeps its inline x-data + existing partials
 *   for now; a future iteration unifies them under this factory.
 */
export function socialTabs(params) {
  const kind = params.kind;
  const ref = params.ref;
  const refPath = encodeURI(ref);
  const followLocked = kind !== 'dp';
  const endorsementTypes = params.endorsementTypes || [];

  function url(suffix) {
    return '/api/social/' + kind + '/' + refPath + suffix;
  }

  return {
    kind,
    ref,
    followLocked,
    endorsementTypes,

    // Endorsements
    endorsementsLoaded: false,
    endorsements: [],
    endorsementBusy: false,

    // Followers
    followersLoaded: false,
    followerCount: 0,
    following: false,
    followBusy: false,

    async init() {
      this._initDeepLink();
      await Promise.all([this.loadEndorsements(), this.loadFollowState()]);
    },

    // Make the social drawer deep-linkable. When this factory is mounted
    // on a Bootstrap offcanvas (the table-detail "Social" drawer), a
    // ``#social`` / ``#social-<tab>`` hash opens the drawer on the right
    // sub-tab, and opening the drawer / switching sub-tab reflects back
    // into the hash so the view can be shared or bookmarked.
    _initDeepLink() {
      const drawer = this.$el;
      if (!drawer || !drawer.classList.contains('offcanvas') || !window.bootstrap) return;
      const activeKey = () => {
        const a = drawer.querySelector('.nav-link.active[data-pql-tab-key]');
        return a ? a.getAttribute('data-pql-tab-key') : null;
      };
      const writeHash = () => {
        const k = activeKey();
        if (k) window.history.replaceState(null, '', '#social-' + k);
      };
      drawer.addEventListener('shown.bs.offcanvas', writeHash);
      drawer.addEventListener('shown.bs.tab', writeHash);
      drawer.addEventListener('hidden.bs.offcanvas', () => {
        if (window.location.hash.indexOf('#social') === 0) {
          window.history.replaceState(null, '', window.location.pathname + window.location.search);
        }
      });
      const m = /^#social(?:-([a-z]+))?$/.exec(window.location.hash);
      if (m) {
        const want = m[1];
        if (want) {
          const btn = drawer.querySelector('[data-pql-tab-key="' + want + '"]');
          if (btn) window.bootstrap.Tab.getOrCreateInstance(btn).show();
        }
        window.bootstrap.Offcanvas.getOrCreateInstance(drawer).show();
      }
    },

    async loadEndorsements() {
      const res = await window.pqlApi.fetch(url('/endorsements'), { silent: true });
      if (!res.ok) {
        this.endorsementsLoaded = true;
        return;
      }
      this.endorsements = (res.data && res.data.endorsements) || [];
      this.endorsementsLoaded = true;
    },

    countForType(typeKey) {
      return this.endorsements.filter((e) => e.endorsement_type === typeKey && !e.removed_at)
        .length;
    },

    mineForType(typeKey) {
      // window.pqlCurrentUserId is undefined when the topbar JS
      // hasn't seeded it (no auth context yet).  Fall back to
      // "any non-removed endorsement of this type" so the toggle
      // still untoggles a row the current user just created in
      // this session — matches the optimistic add path which also
      // doesn't gate on user-id.
      const candidates = this.endorsements.filter(
        (e) => e.endorsement_type === typeKey && !e.removed_at
      );
      if (!candidates.length) return null;
      if (window.pqlCurrentUserId) {
        const mine = candidates.find(
          (e) => e.applied_by && e.applied_by.user_id === window.pqlCurrentUserId
        );
        if (mine) return mine;
      }
      return candidates[0];
    },

    async toggleEndorsement(typeKey) {
      if (this.endorsementBusy) return;
      this.endorsementBusy = true;
      const mine = this.mineForType(typeKey);
      // Optimistic update — flip the row in-memory before the
      // network round-trip so the UI feels instant.  On failure
      // we revert by reloading the canonical list.
      const snapshot = this.endorsements.slice();
      if (mine) {
        this.endorsements = this.endorsements.map((e) =>
          e.id === mine.id ? { ...e, removed_at: new Date().toISOString() } : e
        );
      } else {
        this.endorsements = this.endorsements.concat([
          {
            id: 'optimistic-' + Date.now(),
            endorsement_type: typeKey,
            removed_at: null,
            applied_by: { user_id: window.pqlCurrentUserId },
          },
        ]);
      }
      try {
        let res;
        if (mine) {
          res = await window.pqlApi.fetch(url('/endorsements/' + mine.id), { method: 'DELETE' });
        } else {
          res = await window.pqlApi.fetch(url('/endorsements'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ endorsement_type: typeKey }),
          });
        }
        if (!res || !res.ok) {
          this.endorsements = snapshot;
          if (window.pqlToast) window.pqlToast.error('Endorsement toggle failed.');
          return;
        }
        await this.loadEndorsements();
      } catch (e) {
        this.endorsements = snapshot;
        if (window.pqlToast) window.pqlToast.error('Endorsement toggle failed: ' + e.message);
      } finally {
        this.endorsementBusy = false;
      }
    },

    async loadFollowState() {
      const res = await window.pqlApi.fetch(url('/followers/count'), { silent: true });
      if (!res.ok) {
        this.followersLoaded = true;
        return;
      }
      this.followerCount = (res.data && res.data.count) || 0;
      this.following = !!(res.data && res.data.following);
      this.followersLoaded = true;
    },

    async toggleFollow() {
      if (this.followLocked || this.followBusy) return;
      this.followBusy = true;
      // Optimistic flip — toggle local state before the request
      // resolves so the button reacts instantly.
      const wasFollowing = this.following;
      const prevCount = this.followerCount;
      this.following = !wasFollowing;
      this.followerCount = wasFollowing ? prevCount - 1 : prevCount + 1;
      try {
        const method = wasFollowing ? 'DELETE' : 'POST';
        const res = await window.pqlApi.fetch(url('/follow'), { method });
        if (!res.ok) {
          this.following = wasFollowing;
          this.followerCount = prevCount;
          if (window.pqlToast) window.pqlToast.error('Follow toggle failed.');
          return;
        }
        await this.loadFollowState();
      } catch (e) {
        this.following = wasFollowing;
        this.followerCount = prevCount;
        if (window.pqlToast) window.pqlToast.error('Follow toggle failed: ' + e.message);
      } finally {
        this.followBusy = false;
      }
    },
  };
}
