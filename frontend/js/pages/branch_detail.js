// Auto-extracted from frontend/templates/pages/branch_detail.html.
// Exports: branchDiscussion.
//
// branchDiscussion Alpine factory (mirrors
// tableDiscussion on the table page; separate name so the two
// don't share state when a single Alpine app is mounted across
// both pages by the same user navigating quickly).
export function branchDiscussion(ref) {
    const url = '/api/social/branch/' + encodeURI(ref) + '/comments';
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

window.branchDiscussion = branchDiscussion;
