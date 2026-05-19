/**
 * Phase 95.2 — Cell-level social: inline thread below each cell.
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
        // Phase 95.3 consolidated the cell-tag picker state into this
        // factory because a separately-nested ``cellTagPicker`` x-data
        // received a snapshotted ``cell`` POJO instead of the live
        // reactive proxy — the picker's mutations never reached the
        // parent's ``cells[i].tags``.  Sharing one scope per cell wrapper
        // avoids the Alpine factory-arg snapshot trap entirely.
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
        // Phase 96 — accepted ``pql_explain_cell`` payloads attached
        // to this cell.  Lazily fetched on first open via the
        // /api/notebook/chat/cell/{uuid}/explanations route.
        explanations: [],
        explanationsLoaded: false,

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

        get cellUuid() {
            return this.cellRef ? this.cellRef.cell_uuid : null;
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
                // Phase 96 — explanations live on a separate route
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
                // route is missing (server older than Phase 96).
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

        // ---- Phase 95.3 cell-tag picker — UI state only ----
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
