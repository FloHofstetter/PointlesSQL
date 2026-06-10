/**
 * Feed page — Stream organisation — needs-you inbox, hotkeys, and the seen-cursor.
 *
 * One slice of the ``feedPage`` Alpine factory.  ``installFeedTriage`` mutates
 * the shared component object in place (the project's mixin-installer
 * pattern, mirroring ``installFeedSocial``); ``this`` resolves to the live
 * component at call time, so the method bodies are unchanged from the
 * original single-file factory.
 */

export function installFeedTriage(state) {
  Object.assign(state, {
    // Keyboard navigation — j/k/o/e/m/r/?.
    _focusedIndex: -1,
    _hotkeysAttached: false,

    _installHotkeys() {
      if (this._hotkeysAttached) return;
      this._hotkeysAttached = true;
      window.addEventListener('keydown', (ev) => this._onHotkey(ev));
    },

    _onHotkey(ev) {
      // Don't hijack when the user is typing in a form field.
      const t = ev.target;
      const tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) {
        return;
      }
      // Don't hijack when a modifier is held — Cmd+R must reload.
      if (ev.ctrlKey || ev.metaKey || ev.altKey) return;

      const flat = this._flatRows();
      switch (ev.key) {
        case 'j':
          ev.preventDefault();
          this._focusedIndex = Math.min(flat.length - 1, this._focusedIndex + 1);
          this._highlightFocused();
          break;
        case 'k':
          ev.preventDefault();
          this._focusedIndex = Math.max(0, this._focusedIndex - 1);
          this._highlightFocused();
          break;
        case 'o':
        case 'Enter': {
          const row = flat[this._focusedIndex];
          if (row && row.source_url) {
            ev.preventDefault();
            window.location.href = row.source_url;
          }
          break;
        }
        case 'e': {
          const row = flat[this._focusedIndex];
          if (row && row.kind === 'notification') {
            ev.preventDefault();
            this.toggleRead(row);
          }
          break;
        }
        case 'm': {
          const row = flat[this._focusedIndex];
          if (row) {
            ev.preventDefault();
            this.muteThread(row);
          }
          break;
        }
        case 'r':
          ev.preventDefault();
          {
            const input = document.querySelector('.pql-feed-search');
            if (input) input.focus();
          }
          break;
        case '?':
          ev.preventDefault();
          if (window.bootstrap?.Modal) {
            const el = document.getElementById('pql-feed-help-modal');
            if (el) window.bootstrap.Modal.getOrCreateInstance(el).show();
          }
          break;
        default:
          break;
      }
    },

    _flatRows() {
      // Match rendered DOM order: the pinned "needs you" zone first,
      // then the day-grouped stream (hidden in focus mode).
      const out = [...this.needsYouRows];
      if (!this.focusMode) {
        for (const day of this.groupedDays) {
          for (const r of day.rows) out.push(r);
        }
      }
      return out;
    },

    _highlightFocused() {
      // Drop the focus class from every item, then apply to the n-th
      // rendered card. Card DOM order matches ``_flatRows`` because Alpine
      // renders ``groupedDays`` in the same order.
      const cards = document.querySelectorAll('.pql-feed-item');
      cards.forEach((el) => {
        el.classList.remove('pql-feed-item--focused');
      });
      const target = cards[this._focusedIndex];
      if (target) {
        target.classList.add('pql-feed-item--focused');
        target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    },

    // Is this row part of the finite "needs you" inbox?  Unresolved
    // act work (approvals / open signals) always is; a for_you
    // notification is until it's read.  The resolved/read transition is
    // what drains the zone live.
    _inNeedsYou(r) {
      if (r._resolved) return false;
      if (r.attention === 'act') return true;
      return r.attention === 'for_you' && !r.read_at;
    },

    // Composite stream key, shared by the x-for :key and the caught-up
    // boundary lookup so the two never drift.
    _rowKey(r) {
      return (
        r.kind +
        ':' +
        r.created_at +
        ':' +
        r.event_type +
        ':' +
        (r.entity_ref || '') +
        ':' +
        (r.comment_id || '')
      );
    },

    // True for the single row the caught-up divider renders above.
    isCaughtUpBoundary(r) {
      const key = this._streamBoundaryKey;
      return key !== null && this._rowKey(r) === key;
    },

    // Re-derive the unseen tally from the current rows after a local
    // mutation (drain / scroll-advance), and refresh ``caughtUp``.
    _recomputeUnseen() {
      this.unseenCount = this.streamRows.filter((r) => !!r.is_new).length;
      this.caughtUp =
        this.unseenCount === 0 && this.needsActionCount === 0 && this.unreadForYouCount === 0;
    },

    // Scroll-driven seen-cursor: as the reader scrolls past new stream
    // rows they become "seen", so advance the cursor to the newest row
    // that has crossed the read line.  Reads the DOM fresh on each scan
    // so it survives Alpine re-renders, and only ever moves forward.
    _installSeenAutoAdvance() {
      if (this._seenAutoAttached) return;
      this._seenAutoAttached = true;
      window.addEventListener('scroll', () => this._scheduleSeenScan(), { passive: true });
    },

    _scheduleSeenScan() {
      if (this._seenScanPending) return;
      this._seenScanPending = true;
      window.setTimeout(() => {
        this._seenScanPending = false;
        this._scanSeen();
      }, 500);
    },

    _scanSeen() {
      if (!this.loaded || this.focusMode || this.unseenCount === 0) return;
      // Only count what the reader could actually have looked at.
      if (document.hidden || (document.hasFocus && !document.hasFocus())) return;
      const cards = document.querySelectorAll('.pql-feed-rows .pql-feed-item[data-feed-ts]');
      let maxTs = null;
      cards.forEach((el) => {
        // A card whose top has scrolled to/above the comfortable read
        // line counts as seen.
        if (el.getBoundingClientRect().top < 120) {
          const ts = el.getAttribute('data-feed-ts');
          if (ts && (maxTs === null || ts > maxTs)) maxTs = ts;
        }
      });
      if (maxTs) this._advanceSeenTo(maxTs);
    },

    async _advanceSeenTo(ts) {
      // Forward-only: a stale scan can never rewind the cursor.
      if (this.seenAt && String(ts) <= String(this.seenAt)) return;
      let changed = false;
      this.rows.forEach((r) => {
        if (r.is_new && String(r.created_at) <= String(ts)) {
          r.is_new = false;
          changed = true;
        }
      });
      if (!changed) return;
      this.seenAt = ts;
      this._recomputeUnseen();
      try {
        await fetch('/api/feed/seen', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ at: ts }),
        });
      } catch (e) {
        /* best-effort — the cursor re-syncs on the next reload */
      }
    },

    // Advance the seen-cursor to now and optimistically collapse the
    // stream to "caught up": every rendered row is marked seen and the
    // unseen tally zeroed, so the divider jumps to the top without a
    // reload.
    async markCaughtUp() {
      try {
        const res = await fetch('/api/feed/seen', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.seenAt = data.seen_at || this.seenAt;
      } catch (e) {
        console.error('markCaughtUp failed', e);
        window.pqlToast?.error?.('Could not update your place.');
        return;
      }
      this.rows.forEach((r) => {
        r.is_new = false;
      });
      this.unseenCount = 0;
      this.caughtUp = this.needsActionCount === 0 && this.unreadForYouCount === 0;
    },

    toggleFocusMode() {
      this.focusMode = !this.focusMode;
      try {
        window.localStorage?.setItem('pql.feed.focus', this.focusMode ? '1' : '0');
      } catch (e) {
        /* ignore */
      }
    },

    // Reflect the live "needs you" total in the browser-tab title so a
    // pending count is visible even when the feed is scrolled away or in
    // a background tab.  Driven by x-effect, so it tracks the zone
    // draining without a manual call.  htmx restores the plain title
    // from the next page's <title> on navigation.
    updateTitle() {
      const n = (this.needsActionCount || 0) + (this.unreadForYouCount || 0);
      const base = 'Home · PointlesSQL';
      try {
        document.title = n > 0 ? `(${n}) ${base}` : base;
      } catch (e) {
        /* ignore */
      }
    },
  });
}
