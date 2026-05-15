/*
 * PointlesSQL polymorphic social-tabs Alpine factory (Phase 77.1.5).
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
 * * No DP-page migration in this phase: ``data_product.html`` keeps
 *   its inline x-data + existing partials.  Phase 77.11 unifies.
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
            await Promise.all([
                this.loadEndorsements(),
                this.loadFollowState(),
            ]);
        },

        async loadEndorsements() {
            const res = await window.pqlApi.fetch(url('/endorsements'));
            if (!res.ok) {
                this.endorsementsLoaded = true;
                return;
            }
            const j = await res.json();
            this.endorsements = j.endorsements || [];
            this.endorsementsLoaded = true;
        },

        countForType(typeKey) {
            return this.endorsements.filter(
                (e) => e.endorsement_type === typeKey && !e.removed_at,
            ).length;
        },

        mineForType(typeKey) {
            return this.endorsements.find(
                (e) =>
                    e.endorsement_type === typeKey &&
                    !e.removed_at &&
                    e.applied_by &&
                    e.applied_by.user_id === window.pqlCurrentUserId,
            );
        },

        async toggleEndorsement(typeKey) {
            if (this.endorsementBusy) return;
            this.endorsementBusy = true;
            try {
                const mine = this.mineForType(typeKey);
                if (mine) {
                    await window.pqlApi.fetch(
                        url('/endorsements/' + mine.id),
                        { method: 'DELETE' },
                    );
                } else {
                    await window.pqlApi.fetch(url('/endorsements'), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ endorsement_type: typeKey }),
                    });
                }
                await this.loadEndorsements();
            } finally {
                this.endorsementBusy = false;
            }
        },

        async loadFollowState() {
            const res = await window.pqlApi.fetch(url('/followers/count'));
            if (!res.ok) {
                this.followersLoaded = true;
                return;
            }
            const j = await res.json();
            this.followerCount = j.count || 0;
            this.following = !!j.following;
            this.followersLoaded = true;
        },

        async toggleFollow() {
            if (this.followLocked || this.followBusy) return;
            this.followBusy = true;
            try {
                const method = this.following ? 'DELETE' : 'POST';
                const res = await window.pqlApi.fetch(url('/follow'), {
                    method,
                });
                if (!res.ok) {
                    if (window.pqlToast) {
                        window.pqlToast.error('Follow toggle failed.');
                    }
                    return;
                }
                await this.loadFollowState();
            } finally {
                this.followBusy = false;
            }
        },
    };
}
