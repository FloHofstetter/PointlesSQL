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
    }
  });
}
