// User-profile page factory.  Wraps the per-user dashboard at
// /users/{id} with follow / edit-bio / load-aggregated-counts logic.

export function userProfile(target, ctx) {
  ctx = ctx || {};
  return {
    target: target,
    currentUserId: ctx.current_user_id || 0,
    isAdmin: !!ctx.is_admin,
    loaded: false,
    profile: {
      user_id: target.user_id,
      email: target.email,
      display_name: target.display_name,
      bio_md: '',
      location: null,
    },
    counts: {},
    stewarded: [],
    badges: [],
    recentComments: [],
    recentReviews: [],
    viewerFollows: false,
    editing: false,
    bioDraft: '',
    locationDraft: '',

    get canEdit() {
      return this.isAdmin || this.profile.user_id === this.currentUserId;
    },

    async init() {
      await this.load();
    },

    async load() {
      try {
        const res = await fetch('/api/users/' + this.target.user_id + '/profile');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.profile = data.profile;
        this.counts = data.counts || {};
        this.stewarded = data.stewarded_dps || [];
        this.badges = data.badges || [];
        this.recentComments = data.recent_comments || [];
        this.recentReviews = data.recent_reviews || [];
        this.viewerFollows = !!data.viewer_follows;
        this.bioDraft = this.profile.bio_md || '';
        this.locationDraft = this.profile.location || '';
      } catch (e) {
        console.error('profile load failed', e);
      } finally {
        this.loaded = true;
      }
    },

    async save() {
      try {
        const res = await fetch('/api/users/' + this.target.user_id + '/profile', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            bio_md: this.bioDraft,
            location: this.locationDraft || null,
          }),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.editing = false;
        await this.load();
      } catch (e) {
        console.error('profile save failed', e);
      }
    },

    async follow() {
      try {
        const res = await fetch('/api/users/' + this.target.user_id + '/follow', {
          method: 'POST',
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.viewerFollows = true;
        window.pqlToast?.success(`Now following ${this.target.display_name || 'user'}.`);
        await this.load();
      } catch (e) {
        console.error('follow failed', e);
        window.pqlToast?.error(`Failed to follow: ${e.message}`);
      }
    },

    async unfollow() {
      try {
        const res = await fetch('/api/users/' + this.target.user_id + '/follow', {
          method: 'DELETE',
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.viewerFollows = false;
        window.pqlToast?.success(`Unfollowed ${this.target.display_name || 'user'}.`);
        await this.load();
      } catch (e) {
        console.error('unfollow failed', e);
        window.pqlToast?.error(`Failed to unfollow: ${e.message}`);
      }
    },
  };
}
