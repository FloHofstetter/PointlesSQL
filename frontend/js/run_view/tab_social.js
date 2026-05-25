// Auto-extracted from frontend/templates/pages/_partials/run_view/tab_social.html.
// Exports: runDiscussion.
//
// runDiscussion Alpine factory for the inline
// Discussion sub-tab on /runs/{id}.  Mirrors modelDiscussion exactly
// — the only difference is the endpoint base.  The existing
// _discussion_pane.html partial is data_product.html-coupled, so
// this inline copy lives unifies the discussion
// surface across every kind.
export function runDiscussion(ref) {
    const url = '/api/social/run/' + encodeURI(ref) + '/comments';
    return {
        ref,
        commentsLoaded: false,
        comments: [],
        draftBody: '',
        postBusy: false,

        async init() {
            await this.loadComments();
        },

        async loadComments() {
            const res = await window.pqlApi.fetch(url, { silent: true });
            if (!res.ok) {
                this.commentsLoaded = true;
                return;
            }
            this.comments = (res.data && res.data.comments) || [];
            this.commentsLoaded = true;
        },

        async submitNew() {
            const body = this.draftBody.trim();
            if (!body || this.postBusy) return;
            this.postBusy = true;
            try {
                const res = await window.pqlApi.fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ body_md: body }),
                });
                if (!res.ok) {
                    if (window.pqlToast) window.pqlToast.error('Comment failed to post.');
                    return;
                }
                this.draftBody = '';
                await this.loadComments();
            } finally {
                this.postBusy = false;
            }
        },

        async deleteComment(commentId) {
            if (!window.confirm('Soft-delete this comment?')) return;
            const res = await window.pqlApi.fetch(url + '/' + commentId, {
                method: 'DELETE',
            });
            if (!res.ok) {
                if (window.pqlToast) window.pqlToast.error('Delete failed.');
                return;
            }
            await this.loadComments();
        },
    };
}

window.runDiscussion = runDiscussion;
