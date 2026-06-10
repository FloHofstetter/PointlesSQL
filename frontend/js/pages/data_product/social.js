/**
 * Data-product detail page — Discussion, reviews, reactions, and follow state.
 *
 * One slice of the ``dataProductDetail`` Alpine factory.  ``installDpSocial``
 * mutates the shared component object in place (the project's mixin-installer
 * pattern); ``this`` resolves to the live component at call time, so the
 * method bodies are unchanged from the original single-file factory.
 */

export function installDpSocial(state) {
  Object.assign(state, {
    async loadFollowState() {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/followers/count',
        { silent: true }
      );
      if (!res.ok) {
        console.error('follow state failed', new Error('HTTP ' + res.status));
        return;
      }
      const data = res.data || {};
      this.following = !!data.following;
      this.followersCount = data.count || 0;
    },

    async toggleFollow() {
      const method = this.following ? 'DELETE' : 'POST';
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/follow',
        { method: method, silent: true }
      );
      if (!res.ok) {
        console.error('follow toggle failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadFollowState();
    },

    async loadReviewSummary() {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reviews',
        { silent: true }
      );
      if (!res.ok) {
        console.error('review summary failed', new Error('HTTP ' + res.status));
        return;
      }
      const data = res.data || {};
      this.reviewSummary = data.summary;
      this.myReview = data.my_review;
    },

    async loadReviews() {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reviews',
        { silent: true }
      );
      if (!res.ok) {
        console.error('reviews load failed', new Error('HTTP ' + res.status));
        this.reviewsLoaded = true;
        return;
      }
      const data = res.data || {};
      this.reviews = data.reviews || [];
      this.reviewSummary = data.summary;
      this.myReview = data.my_review;
      if (this.myReview) {
        this.reviewDraftStars = this.myReview.stars;
        this.reviewDraftBody = this.myReview.body_md || '';
      }
      this.reviewsLoaded = true;
    },

    async submitReview() {
      if (this.reviewDraftStars < 1 || this.reviewDraftStars > 5) return;
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reviews',
        {
          method: 'PUT',
          body: { stars: this.reviewDraftStars, body_md: this.reviewDraftBody },
          silent: true,
        }
      );
      if (!res.ok) {
        console.error('review post failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadReviews();
    },

    async deleteOwnReview() {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reviews',
        { method: 'DELETE', silent: true }
      );
      if (!res.ok) {
        console.error('review delete failed', new Error('HTTP ' + res.status));
        return;
      }
      this.reviewDraftStars = 0;
      this.reviewDraftBody = '';
      await this.loadReviews();
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
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/activity?limit=100',
        { silent: true }
      );
      if (!res.ok) {
        console.error('activity load failed', new Error('HTTP ' + res.status));
        this.activityLoaded = true;
        return;
      }
      this.activity = (res.data && res.data.activity) || [];
      this.activityTotal = this.activity.length;
      this.activityLoaded = true;
    },

    async loadComments() {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/comments',
        { silent: true }
      );
      if (!res.ok) {
        console.error('comments load failed', new Error('HTTP ' + res.status));
        this.commentsLoaded = true;
        return;
      }
      this.comments = (res.data && res.data.comments) || [];
      this.commentsTotal = this.comments.length;
      this.commentsLoaded = true;
    },

    async submitNew() {
      const body = this.newCommentDraft.trim();
      if (!body) return;
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/comments',
        {
          method: 'POST',
          body: {
            body_md: body,
            category: this.newCommentCategory || 'general',
          },
          silent: true,
        }
      );
      if (!res.ok) {
        console.error('comment post failed', new Error('HTTP ' + res.status));
        return;
      }
      this.newCommentDraft = '';
      this.newCommentCategory = 'general';
      await this.loadComments();
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
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/comments/' +
          replyId +
          '/accept-answer',
        { method: 'POST', silent: true }
      );
      if (!res.ok) {
        console.error('accept-answer failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadComments();
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
      let res;
      if (row && row.has_current_user_reacted) {
        res = await window.pqlApi.fetch(url + '/' + encodeURIComponent(emoji), {
          method: 'DELETE',
          silent: true,
        });
      } else {
        res = await window.pqlApi.fetch(url, {
          method: 'POST',
          body: { emoji: emoji },
          silent: true,
        });
      }
      if (!res.ok) {
        console.error('comment reaction toggle failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadComments();
    },

    async loadDpReactions() {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reactions',
        { silent: true }
      );
      if (!res.ok) {
        console.error('dp reactions load failed', new Error('HTTP ' + res.status));
        return;
      }
      const next = {};
      for (const r of (res.data && res.data.reactions) || []) {
        next[r.emoji] = { count: r.count, mine: r.has_current_user_reacted };
      }
      this.dpReactions = next;
    },

    async toggleDpReaction(emoji) {
      const current = this.dpReactions[emoji];
      const url =
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/reactions';
      let res;
      if (current && current.mine) {
        res = await window.pqlApi.fetch(url + '/' + encodeURIComponent(emoji), {
          method: 'DELETE',
          silent: true,
        });
      } else {
        res = await window.pqlApi.fetch(url, {
          method: 'POST',
          body: { emoji: emoji },
          silent: true,
        });
      }
      if (!res.ok) {
        console.error('dp reaction toggle failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadDpReactions();
    },

    async submitReply(parentId) {
      const body = this.replyDraft.trim();
      if (!body) return;
      const res = await window.pqlApi.fetch(
        '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/comments',
        {
          method: 'POST',
          body: { body_md: body, parent_comment_id: parentId },
          silent: true,
        }
      );
      if (!res.ok) {
        console.error('reply post failed', new Error('HTTP ' + res.status));
        return;
      }
      this.replyingTo = null;
      this.replyDraft = '';
      await this.loadComments();
    },

    async deleteComment(id) {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          this.product.catalog +
          '/' +
          this.product.schema +
          '/comments/' +
          id,
        { method: 'DELETE', silent: true }
      );
      if (!res.ok) {
        console.error('comment delete failed', new Error('HTTP ' + res.status));
        return;
      }
      await this.loadComments();
    },
  });
}
