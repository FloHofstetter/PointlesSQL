/**
 * Feed engagement mixin — emoji reactions + reply, wired onto the
 * ``feedPage`` Alpine factory.
 *
 * The platform already exposes polymorphic social endpoints keyed by
 * ``(entity_kind, entity_ref)`` — exactly what every feed row carries —
 * so reactions need no new backend:
 *
 *   GET    /api/social/{kind}/{ref}/comments/{id}/reactions
 *   POST   /api/social/{kind}/{ref}/comments/{id}/reactions   {emoji}
 *   DELETE /api/social/{kind}/{ref}/comments/{id}/reactions/{emoji}
 *
 * Reactions attach to comments only (reviews carry their own star rating).
 * Reaction summaries lazy-load after the feed renders; toggles are
 * optimistic and revert on error.
 */

import { escapeHtml, renderInlineMd } from './inline_md.js';

// The canonical six-emoji palette the server's ``ALLOWED_EMOJI`` accepts.
const REACTION_PALETTE = ['👍', '❤️', '🎉', '😄', '😕', '👀'];
// Accessible names for each emoji, for screen-reader labels on the
// palette buttons.
const EMOJI_LABELS = {
  '👍': 'thumbs up',
  '❤️': 'heart',
  '🎉': 'celebrate',
  '😄': 'smile',
  '😕': 'confused',
  '👀': 'eyes',
};

// Render one emoji's reactor list as "You, Mara and 3 others".  The
// backend puts the caller first, flagged by ``has_current_user_reacted``.
function formatReactorNames(group) {
  const names = (group.users || []).map((u) => u.display_name);
  if (group.has_current_user_reacted && names.length) names[0] = 'You';
  if (names.length <= 3) return names.join(', ');
  return `${names.slice(0, 2).join(', ')} and ${names.length - 2} others`;
}

export function installFeedSocial(state) {
  state.reactionPalette = REACTION_PALETTE;

  // Screen-reader label for a palette button ("React thumbs up").
  state.emojiLabel = (emoji) => `React ${EMOJI_LABELS[emoji] || emoji}`;

  // Whether the current user already reacted with this emoji — drives the
  // active ring in the palette so the picker reflects current state.
  state.hasReacted = (r, emoji) => (r._reactions || []).some((x) => x.emoji === emoji && x.mine);

  // Reaction target URL for a row.  Comments key on ``comment_id``;
  // reviews key on ``review_id`` (a per-review endpoint — reviews of one
  // product share a social anchor, so an entity-level reaction would move
  // every sibling review's count together).  Both endpoints share the
  // same shape (POST base, DELETE base/{emoji}, GET base), so the toggle
  // and load helpers below are kind-agnostic.
  state._reactBase = (r) => {
    if (!r || !r.entity_kind || !r.entity_ref) return null;
    const kind = encodeURIComponent(String(r.entity_kind));
    const ref = encodeURI(String(r.entity_ref));
    if (r.comment_id) {
      return `/api/social/${kind}/${ref}/comments/${r.comment_id}/reactions`;
    }
    if (r.render_kind === 'review' && r.review_id) {
      return `/api/social/${kind}/${ref}/reviews/${r.review_id}/reactions`;
    }
    return null;
  };

  state.canReact = function (r) {
    return !!this._reactBase(r);
  };

  // Lazy-load reaction summaries for a batch of rows after the feed
  // renders.  Bounded so a long feed doesn't fan out hundreds of GETs.
  state._loadReactionsFor = async function (rows) {
    const targets = (rows || [])
      .filter((r) => this.canReact(r) && !r._reactionsLoaded)
      .slice(0, 40);
    await Promise.all(targets.map((r) => this._loadReactions(r)));
  };

  state._loadReactions = async function (r) {
    const base = this._reactBase(r);
    if (!base) return;
    r._reactionsLoaded = true;
    try {
      // silent: this is an optional background GET fanned out across up to
      // 40 rows — a transient endpoint failure must not flood the user with
      // a wall of error toasts (api.js auto-toasts non-ok unless silenced).
      const res = await window.pqlApi.fetch(base, { method: 'GET', silent: true });
      if (res.ok && res.data && Array.isArray(res.data.reactions)) {
        r._reactions = res.data.reactions.map((x) => ({
          emoji: x.emoji,
          count: x.count || 0,
          mine: !!x.has_current_user_reacted,
        }));
      }
    } catch (_e) {
      /* best-effort — a failed summary just leaves the row un-chipped */
    }
  };

  // Chips to render — only emoji that actually have a reaction.
  state.activeReactions = (r) => (r._reactions || []).filter((x) => x.count > 0);

  // Who-reacted: load reactor identities on demand (a single GET with
  // ``?with_names=1``), triggered when the user hovers a reaction chip —
  // names aren't needed until then, so the bulk fan-out stays count-only.
  state.loadReactors = async function (r) {
    const base = this._reactBase(r);
    if (!base || r._reactorsLoaded) return;
    r._reactorsLoaded = true;
    const res = await window.pqlApi.fetch(`${base}?with_names=1`, {
      method: 'GET',
      silent: true,
    });
    if (res.ok && res.data && Array.isArray(res.data.reactions)) {
      r._reactors = res.data.reactions;
    }
  };

  // Who reacted with one emoji — "You, Mara and 3 others" — for the chip's
  // hover title.  Empty until ``loadReactors`` has run.
  state.chipReactors = (r, emoji) => {
    const group = (r._reactors || []).find((x) => x.emoji === emoji);
    return group && group.count ? formatReactorNames(group) : '';
  };

  state._findReaction = (r, emoji) => {
    if (!Array.isArray(r._reactions)) {
      r._reactions = REACTION_PALETTE.map((e) => ({ emoji: e, count: 0, mine: false }));
    }
    let row = r._reactions.find((x) => x.emoji === emoji);
    if (!row) {
      row = { emoji, count: 0, mine: false };
      r._reactions.push(row);
    }
    return row;
  };

  // Optimistic toggle — flip ``mine`` + adjust the count immediately,
  // then reconcile with the server and revert on failure.
  state.toggleReaction = async function (r, emoji) {
    const base = this._reactBase(r);
    if (!base) return;
    const cur = this._findReaction(r, emoji);
    const wasMine = cur.mine;
    cur.mine = !wasMine;
    cur.count = Math.max(0, cur.count + (wasMine ? -1 : 1));
    r._reactPickerOpen = false;
    // Pop the chip on add (not removal) — a brief scale bump confirms it.
    if (!wasMine) {
      r._poppedEmoji = emoji;
      window.setTimeout(() => {
        if (r._poppedEmoji === emoji) r._poppedEmoji = null;
      }, 220);
    }
    const res = wasMine
      ? await window.pqlApi.fetch(`${base}/${encodeURIComponent(emoji)}`, { method: 'DELETE' })
      : await window.pqlApi.fetch(base, { method: 'POST', body: { emoji } });
    if (!res.ok) {
      cur.mine = wasMine;
      cur.count = Math.max(0, cur.count + (wasMine ? 1 : -1));
    }
  };

  state.toggleReactPicker = (r) => {
    r._reactPickerOpen = !r._reactPickerOpen;
  };

  // Comments base URL for a row (distinct from the reactions base).
  state._commentsBase = (r) => {
    if (!r || !r.entity_kind || !r.entity_ref) return null;
    return `/api/social/${encodeURIComponent(String(r.entity_kind))}/${encodeURI(String(r.entity_ref))}/comments`;
  };

  // ---- Inline reply -------------------------------------------------
  // Reply is comment-only — a comment carries a ``comment_id`` to thread
  // under.  Reviews reach this footer (for reactions) but have no comment
  // to reply to, so they get no reply affordance.
  state.canReply = (r) => !!(r && r.comment_id);

  state.toggleReply = (r) => {
    r._replyOpen = !r._replyOpen;
  };

  state.postReply = async function (r) {
    const bodyMd = (r._replyDraft || '').trim();
    if (!bodyMd || !r.comment_id || r._replyBusy) return;
    const base = this._commentsBase(r);
    if (!base) return;
    r._replyBusy = true;
    const res = await window.pqlApi.fetch(base, {
      method: 'POST',
      body: { body_md: bodyMd, parent_comment_id: r.comment_id },
    });
    r._replyBusy = false;
    if (!res.ok) return;
    // Optimistically thread the new reply under the comment + bump the
    // count so "View N replies" updates without a reload.
    const created = res.data || {};
    r._replies = (r._replies || []).concat([created]);
    r._replyCount = (r._replyCount ?? r.reply_count ?? 0) + 1;
    r.reply_count = (r.reply_count || 0) + 1;
    r._threadOpen = true;
    r._replyDraft = '';
    r._replyOpen = false;
    window.pqlToast?.success?.('Reply posted.');
  };

  // ---- Inline thread (replies under a comment) ---------------------
  // Replies render as a pre-built HTML string (no ``<template x-for>``)
  // because the thread starts collapsed; an x-for created in a hidden
  // subtree loses its anchor.  Bodies go through ``renderInlineMd``
  // (escape-first) and author names through ``escapeHtml``, so the
  // x-html sink only ever receives safe markup.
  state.replyTotal = (r) => r._replyCount ?? r.reply_count ?? 0;
  state.hasReplies = (r) => state.replyTotal(r) > 0;
  state.replyLabel = (r) => {
    const n = state.replyTotal(r);
    return `${r._threadOpen ? 'Hide' : 'View'} ${n} ${n === 1 ? 'reply' : 'replies'}`;
  };

  state.toggleThread = async function (r) {
    r._threadOpen = !r._threadOpen;
    if (r._threadOpen) await this.loadThread(r);
  };

  state.loadThread = async function (r) {
    const base = this._commentsBase(r);
    if (!base || !r.comment_id) return;
    const res = await window.pqlApi.fetch(base, { method: 'GET', silent: true });
    if (res.ok && res.data) {
      const all = Array.isArray(res.data) ? res.data : res.data.comments || [];
      r._replies = all.filter((c) => c.parent_comment_id === r.comment_id);
      r._replyCount = r._replies.length;
    }
  };

  state.threadHtml = (r) => {
    const replies = r._replies || [];
    if (!replies.length) return '';
    return replies
      .map((c) => {
        const who = escapeHtml(
          (c.author && (c.author.display_name || c.author.email)) ||
            c.author_display_name ||
            'Someone'
        );
        const body = renderInlineMd(c.body_md || c.body_md_resolved || '');
        return `<div class="pql-feed-thread-item"><span class="pql-feed-thread-item__who">${who}</span> ${body}</div>`;
      })
      .join('');
  };

  // ---- Follow an entity straight from its card ---------------------
  state.followEntity = async (r) => {
    if (!r.entity_kind || !r.entity_ref) return;
    const url = `/api/social/${encodeURIComponent(String(r.entity_kind))}/${encodeURI(String(r.entity_ref))}/follow`;
    const res = await window.pqlApi.fetch(url, { method: 'POST' });
    // The follow endpoint is idempotent (200 ``{followed, already}``), so a
    // plain ok-check is correct — a repeat follow is not an error.
    if (res.ok) {
      window.pqlToast?.success?.(`Following ${r.entity_ref}.`);
    }
  };

  state.canFollowEntity = (r) =>
    !!r.entity_ref &&
    ['dp', 'table', 'model', 'branch', 'schema', 'catalog'].includes(r.entity_kind);

  // ---- Composer ("share an update") --------------------------------
  // The "post to" product pills are rendered server-side (a <template
  // x-for> nested in the composer's toggled editor loses its anchor in
  // Alpine 3.14), and ``composerTargetRef`` is seeded by an x-init in the
  // template, so no target list is held in JS.
  state.composerOpen = false;
  state.composerDraft = '';
  state.composerTargetRef = '';
  state.composerPosting = false;

  state.openComposer = function () {
    this.composerOpen = true;
  };

  state.closeComposer = function () {
    this.composerOpen = false;
    this.composerDraft = '';
  };

  state.postComposer = async function () {
    const bodyMd = (this.composerDraft || '').trim();
    if (!bodyMd || !this.composerTargetRef || this.composerPosting) return;
    this.composerPosting = true;
    const ref = encodeURI(this.composerTargetRef);
    const res = await window.pqlApi.fetch(`/api/social/dp/${ref}/comments`, {
      method: 'POST',
      body: { body_md: bodyMd },
    });
    this.composerPosting = false;
    if (!res.ok) return;
    const created = res.data || {};
    const author = created.author || {};
    // Optimistic-prepend the post so the author sees it immediately — the
    // "all" feed otherwise only surfaces followed users' comments, never
    // the caller's own.  The POST response carries the real author, so the
    // avatar matches how the user appears everywhere else.
    this.rows.unshift({
      kind: 'comment',
      render_kind: 'comment',
      category: 'social',
      severity: 'info',
      event_type: 'pointlessql.data_product.commented',
      summary_md: bodyMd,
      body_md: bodyMd,
      comment_id: created.id || created.comment_id || null,
      source_url: `/data-products/${this.composerTargetRef.split('.').join('/')}`,
      entity_kind: 'dp',
      entity_ref: this.composerTargetRef,
      actor_user_id: author.user_id || null,
      actor_display_name: author.display_name || 'You',
      created_at: new Date().toISOString(),
      read_at: null,
      _fresh: true,
    });
    this.composerDraft = '';
    this.composerOpen = false;
    window.pqlToast?.success?.(`Posted to ${this.composerTargetRef}.`);
  };
}
