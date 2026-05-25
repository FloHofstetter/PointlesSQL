/**
 * Cell-level social: inline thread below each cell.
 *
 * Mounted per cell as ``x-data="cellThread({ notebookUuid, cellUuid,
 * initialCounts })"`` inside the cell wrapper.  Lazy-loads the thread
 * the first time the chip is toggled open; subsequent toggles just
 * flip ``open`` without re-fetching.  Counts are updated optimistically
 * on POST/DELETE so the chip stays in sync with the open thread.
 *
 * Polymorphic API contract (kind='notebook_cell'):
 *   GET    /api/social/notebook_cell/{nb}:{cell}/comments
 *   POST   /api/social/notebook_cell/{nb}:{cell}/comments    {body_md}
 *   DELETE /api/social/notebook_cell/{nb}:{cell}/comments/{id}
 *   GET    /api/social/notebook_cell/{nb}:{cell}/reactions
 *   POST   /api/social/notebook_cell/{nb}:{cell}/reactions   {emoji}
 *   DELETE /api/social/notebook_cell/{nb}:{cell}/reactions/{emoji}
 *   GET    /api/social/notebook_cell/{nb}:{cell}/followers/count
 *   POST   /api/social/notebook_cell/{nb}:{cell}/follow
 *   DELETE /api/social/notebook_cell/{nb}:{cell}/follow
 */

const ALLOWED_EMOJI = ["👍", "❤️", "🎉", "😄", "😕", "👀"];

// review decisions encoded as a leading body_md
// line.  The polymorphic comments table carries ``category`` but no
// dedicated decision column; adding one would be a migration for what
// is effectively a UI affordance.  Keeping the decision in the body
// keeps the round-trip stable (the JS extracts it back on render) and
// degrades gracefully on older clients that just see a regular review
// comment.
const REVIEW_DECISIONS = [
    { id: "approved", label: "Approved", icon: "bi-check-circle-fill", className: "text-success", prefix: "✅ **Approved**" },
    { id: "changes_requested", label: "Changes requested", icon: "bi-exclamation-triangle-fill", className: "text-warning", prefix: "⚠️ **Changes requested**" },
    { id: "comment", label: "Comment only", icon: "bi-chat-left-text", className: "text-muted", prefix: "💬 **Reviewed**" },
];

function extractReviewDecision(body_md) {
    const head = (body_md || "").split("\n")[0].trim();
    for (const d of REVIEW_DECISIONS) {
        if (head === d.prefix) return d;
    }
    return REVIEW_DECISIONS[2];
}

function csrfTokenFromCookie() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
}

async function jsonFetch(url, options = {}) {
    const headers = Object.assign(
        { "Content-Type": "application/json" },
        options.headers || {},
    );
    const method = (options.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
        const token = csrfTokenFromCookie();
        if (token) headers["X-CSRFToken"] = token;
    }
    const res = await fetch(url, { ...options, headers, credentials: "same-origin" });
    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`${method} ${url} failed: ${res.status} ${text}`);
    }
    if (res.status === 204) return null;
    return res.json();
}

export function cellThread({ notebookUuid, cell, initialCounts, curatedTags = [] } = {}) {
    return {
        notebookUuid: notebookUuid || null,
        // Hold the parent cell reference, not just the UUID snapshot —
        // the UUID is null until the first save mints it, and the
        // factory was capturing the early-null value forever.  Reading
        // ``cell.cell_uuid`` lazily inside the ``baseUrl`` getter makes
        // the thread come alive as soon as the save reconciler returns.
        //
        // The cell-tag picker state lives here so it shares the live
        // reactive ``cell`` proxy.  A separately-nested ``cellTagPicker``
        // x-data received a snapshotted ``cell`` POJO instead — the
        // picker's mutations never reached the parent's
        // ``cells[i].tags``.  Sharing one scope per cell wrapper avoids
        // the Alpine factory-arg snapshot trap entirely.
        cellRef: cell || null,
        curatedTags: Array.isArray(curatedTags)
            ? curatedTags.filter((t) => t && t !== 'parameters')
            : [],
        pickerOpen: false,
        pickerCustomMode: false,
        pickerCustomDraft: '',
        open: false,
        loaded: false,
        loading: false,
        error: null,
        comments: [],
        reactions: ALLOWED_EMOJI.map((e) => ({ emoji: e, count: 0, mine: false })),
        following: false,
        followerCount: 0,
        commentCount: 0,
        draftBody: "",
        submitting: false,
        allowedEmoji: ALLOWED_EMOJI,
        // accepted ``pql_explain_cell`` payloads attached
        // to this cell.  Lazily fetched on first open via the
        // /api/notebook/chat/cell/{uuid}/explanations route.
        explanations: [],
        explanationsLoaded: false,
        // review-compose UI state.
        reviewComposerOpen: false,
        reviewDecision: "approved",
        reviewBody: "",
        reviewSubmitting: false,

        init() {
            if (initialCounts) this._applyCounts(initialCounts);
        },

        get hasActivity() {
            return (
                this.commentCount > 0
                || this.followerCount > 0
                || this.reactions.some((r) => r.count > 0)
            );
        },

        get reviewComments() {
            return this.comments.filter((c) => c.category === "review" && !c.deleted_at);
        },

        get nonReviewComments() {
            return this.comments.filter((c) => c.category !== "review");
        },

        get reviewDecisions() { return REVIEW_DECISIONS; },

        decisionFor(comment) {
            return extractReviewDecision(comment.body_md);
        },

        bodyWithoutPrefix(comment) {
            const d = extractReviewDecision(comment.body_md);
            const body = comment.body_md || "";
            if (body.startsWith(d.prefix)) {
                return body.slice(d.prefix.length).replace(/^\n+/, "");
            }
            return body;
        },

        get approvedReviewCount() {
            return this.reviewComments.filter(
                (c) => this.decisionFor(c).id === "approved",
            ).length;
        },

        get changesRequestedCount() {
            return this.reviewComments.filter(
                (c) => this.decisionFor(c).id === "changes_requested",
            ).length;
        },

        // Resolve the live cell from the parent scope on every read.
        // ``cellRef`` was meant to be a live Alpine proxy but in
        // practice ended up snapshotting ``cell_uuid`` at factory-init
        // time — the save-path mints UUIDs into the parent's
        // ``cells[i]`` proxy without the snapshot ever catching up
        // (caught during replay testing).  Walking the DOM up to the
        // editor scope and looking up by stable ``cell.id`` keeps the
        // thread accurate after a save reconciliation.
        _liveCell() {
            try {
                if (!window.Alpine || !this.$el) return this.cellRef;
                const shell = this.$el.closest('.pql-notebook-shell');
                if (!shell) return this.cellRef;
                const editor = window.Alpine.$data(shell);
                const cellId = this.cellRef?.id;
                if (!editor?.cells || !cellId) return this.cellRef;
                return editor.cells.find((c) => c.id === cellId) || this.cellRef;
            } catch {
                return this.cellRef;
            }
        },

        get cellUuid() {
            const live = this._liveCell();
            return live ? live.cell_uuid : null;
        },

        get baseUrl() {
            const cellUuid = this.cellUuid;
            if (!this.notebookUuid || !cellUuid) return null;
            return `/api/social/notebook_cell/${this.notebookUuid}:${cellUuid}`;
        },

        applyCounts(counts) {
            this._applyCounts(counts);
        },

        _applyCounts(counts) {
            if (!counts) return;
            this.commentCount = counts.comments || 0;
            this.followerCount = counts.followers || 0;
            const reactionMap = counts.reactions || {};
            this.reactions = ALLOWED_EMOJI.map((emoji) => ({
                emoji,
                count: reactionMap[emoji] || 0,
                // mine state needs a per-user GET; only refreshed when the
                // thread is opened.  Initial render is "nobody reacted as me".
                mine: this.reactions.find((r) => r.emoji === emoji)?.mine || false,
            }));
        },

        async toggle() {
            this.open = !this.open;
            if (this.open && !this.loaded && !this.loading) {
                await this.loadAll();
            }
        },

        async loadAll() {
            if (!this.baseUrl) return;
            this.loading = true;
            this.error = null;
            try {
                const [commentsResp, reactionsResp, followersResp] = await Promise.all([
                    jsonFetch(`${this.baseUrl}/comments`),
                    jsonFetch(`${this.baseUrl}/reactions`),
                    jsonFetch(`${this.baseUrl}/followers/count`),
                ]);
                this.comments = commentsResp.comments || [];
                this.commentCount = this.comments.filter((c) => !c.deleted_at).length;
                this._mergeReactionList(reactionsResp.reactions || []);
                this.followerCount = followersResp.count || 0;
                this.following = !!followersResp.following;
                this.loaded = true;
                // explanations live on a separate route
                // because they're keyed on cell_uuid alone (no
                // notebook prefix).  Fetch alongside the social
                // bundle so the section renders immediately.
                await this.loadExplanations();
            } catch (err) {
                this.error = err.message || "load failed";
            } finally {
                this.loading = false;
            }
        },

        async loadExplanations() {
            if (this.explanationsLoaded) return;
            const cellUuid = this.cellUuid;
            if (!cellUuid) return;
            try {
                const resp = await jsonFetch(
                    `/api/notebook/chat/cell/${cellUuid}/explanations`,
                );
                this.explanations = resp.explanations || [];
                this.explanationsLoaded = true;
            } catch (_e) {
                // Non-fatal: tab simply renders empty if the new
                // route is missing on older servers.
                this.explanations = [];
                this.explanationsLoaded = true;
            }
        },

        _mergeReactionList(rows) {
            const byEmoji = new Map(rows.map((r) => [r.emoji, r]));
            this.reactions = ALLOWED_EMOJI.map((emoji) => {
                const row = byEmoji.get(emoji);
                return {
                    emoji,
                    count: row ? row.count : 0,
                    mine: row ? !!row.has_current_user_reacted : false,
                };
            });
        },

        async submitComment() {
            const body = (this.draftBody || "").trim();
            if (!body || this.submitting || !this.baseUrl) return;
            this.submitting = true;
            try {
                const created = await jsonFetch(`${this.baseUrl}/comments`, {
                    method: "POST",
                    body: JSON.stringify({ body_md: body }),
                });
                this.comments.push(created);
                this.commentCount += 1;
                this.draftBody = "";
            } catch (err) {
                this.error = err.message || "post failed";
            } finally {
                this.submitting = false;
            }
        },

        // submit a per-cell review decision.  Posts
        // a comment with ``category='review'`` and a decision-prefix
        // line that the renderer extracts back into the badge + label.
        async submitReview() {
            if (this.reviewSubmitting || !this.baseUrl) return;
            const decision = REVIEW_DECISIONS.find((d) => d.id === this.reviewDecision)
                || REVIEW_DECISIONS[0];
            const body = (this.reviewBody || "").trim();
            const fullBody = body ? `${decision.prefix}\n\n${body}` : decision.prefix;
            this.reviewSubmitting = true;
            try {
                const created = await jsonFetch(`${this.baseUrl}/comments`, {
                    method: "POST",
                    body: JSON.stringify({ body_md: fullBody, category: "review" }),
                });
                this.comments.push(created);
                this.commentCount += 1;
                this.reviewBody = "";
                this.reviewComposerOpen = false;
            } catch (err) {
                this.error = err.message || "review failed";
            } finally {
                this.reviewSubmitting = false;
            }
        },

        toggleReviewComposer() {
            this.reviewComposerOpen = !this.reviewComposerOpen;
            // Auto-open the thread when composing a review so the user
            // can see existing reviews while writing theirs.
            if (this.reviewComposerOpen && !this.open) {
                this.toggle();
            }
        },

        async deleteComment(commentId) {
            if (!this.baseUrl) return;
            try {
                await jsonFetch(`${this.baseUrl}/comments/${commentId}`, {
                    method: "DELETE",
                });
                this.comments = this.comments.filter((c) => c.id !== commentId);
                this.commentCount = Math.max(0, this.commentCount - 1);
            } catch (err) {
                this.error = err.message || "delete failed";
            }
        },

        async toggleReaction(emoji) {
            if (!this.baseUrl) return;
            const current = this.reactions.find((r) => r.emoji === emoji);
            if (!current) return;
            try {
                if (current.mine) {
                    await jsonFetch(
                        `${this.baseUrl}/reactions/${encodeURIComponent(emoji)}`,
                        { method: "DELETE" },
                    );
                    current.mine = false;
                    current.count = Math.max(0, current.count - 1);
                } else {
                    await jsonFetch(`${this.baseUrl}/reactions`, {
                        method: "POST",
                        body: JSON.stringify({ emoji }),
                    });
                    current.mine = true;
                    current.count += 1;
                }
            } catch (err) {
                this.error = err.message || "reaction failed";
            }
        },

        async toggleFollow() {
            if (!this.baseUrl) return;
            try {
                if (this.following) {
                    await jsonFetch(`${this.baseUrl}/follow`, { method: "DELETE" });
                    this.following = false;
                    this.followerCount = Math.max(0, this.followerCount - 1);
                } else {
                    await jsonFetch(`${this.baseUrl}/follow`, { method: "POST" });
                    this.following = true;
                    this.followerCount += 1;
                }
            } catch (err) {
                this.error = err.message || "follow failed";
            }
        },

        // ---- Cell-tag picker — UI state only ----
        //
        // Tag mutations live as inline expressions in
        // ``cell_tag_picker.html`` so they reference the live x-for
        // ``cell`` variable directly (Alpine snapshotted ``cell`` when
        // it crossed the cellThread factory boundary).  Only the
        // picker's local UI state (open / customMode / customDraft) +
        // the dropdown-toggle helper live here.
        togglePickerOpen() {
            this.pickerOpen = !this.pickerOpen;
            if (!this.pickerOpen) {
                this.pickerCustomMode = false;
                this.pickerCustomDraft = '';
            }
        },
    };
}
