/**
 * Feed page Alpine factory.
 *
 * The home activity stream. Owns the SSE
 * connection lifecycle, the day-binning getter that groups rows into
 * Today / Yesterday / dated headers, keyboard navigation (j/k/o/e/m/r/?),
 * saved-search bookmarks, and the first-run welcome card.
 *
 * Lifted from the inline ``<script>`` block in
 * ``pages/_partials/feed/scripts.html`` into this ESM module.
 * ``bootstrap.js`` re-attaches the factory to ``window.feedPage`` so
 * the template's ``x-data="feedPage()"`` keeps resolving.
 *
 * The component surface is composed from focused mixin installers under
 * ``feed/`` (state, sse, actions, render, discovery, triage) plus the
 * existing ``installFeedSocial``.  The four derived views stay as native
 * getters on the instance below so Alpine reads them as reactive computed
 * properties.
 */

import { installFeedSocial } from '../feed_social.js';
import { installFeedActions } from './feed/actions.js';
import { installFeedDiscovery } from './feed/discovery.js';
import { installFeedRender } from './feed/render.js';
import { installFeedSse } from './feed/sse.js';
import { installFeedState } from './feed/state.js';
import { installFeedTriage } from './feed/triage.js';

const DAY_MS = 24 * 60 * 60 * 1000;

function _todayStart() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function _dayLabel(rowDate, todayStart) {
  const dayStart = new Date(rowDate);
  dayStart.setHours(0, 0, 0, 0);
  const diffDays = Math.round((todayStart.getTime() - dayStart.getTime()) / DAY_MS);
  if (diffDays <= 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays > 14) return 'Earlier';
  return dayStart.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

function _dayIso(rowDate, todayStart) {
  const dayStart = new Date(rowDate);
  dayStart.setHours(0, 0, 0, 0);
  const diffDays = Math.round((todayStart.getTime() - dayStart.getTime()) / DAY_MS);
  if (diffDays > 14) return 'earlier';
  return dayStart.toISOString().slice(0, 10);
}

export function feedPage(isAdmin = false) {
  const obj = {

    // The pinned inbox zone — act rows first (by severity), then
    // for_you (newest first).  A row appears here OR in the stream,
    // never both.
    get needsYouRows() {
      const sevRank = { error: 0, warn: 1, info: 2 };
      return this.rows
        .filter((r) => this._inNeedsYou(r))
        .slice()
        .sort((a, b) => {
          const aAct = a.attention === 'act' ? 0 : 1;
          const bAct = b.attention === 'act' ? 0 : 1;
          if (aAct !== bAct) return aAct - bAct;
          if (aAct === 0) {
            const sa = sevRank[a.severity] ?? 3;
            const sb = sevRank[b.severity] ?? 3;
            if (sa !== sb) return sa - sb;
          }
          return String(b.created_at).localeCompare(String(a.created_at));
        });
    },

    // The infinite ambient stream — everything not pinned into the
    // inbox zone above.
    get streamRows() {
      return this.rows.filter((r) => !this._inNeedsYou(r));
    },

    // Key of the first already-seen stream row — where the "you're all
    // caught up" divider sits.  Null when every stream row is still new
    // (nothing seen yet to divide against).
    get _streamBoundaryKey() {
      const seen = this.streamRows.find((r) => !r.is_new);
      return seen ? this._rowKey(seen) : null;
    },

    get groupedDays() {
      const todayStart = _todayStart();
      const groups = new Map();
      for (const r of this.streamRows) {
        const rowDate = new Date(r.created_at);
        if (Number.isNaN(rowDate.getTime())) continue;
        const iso = _dayIso(rowDate, todayStart);
        if (!groups.has(iso)) {
          groups.set(iso, {
            iso,
            label: _dayLabel(rowDate, todayStart),
            rows: [],
          });
        }
        groups.get(iso).rows.push(r);
      }
      // Sort groups: "today" first, then iso desc, then "earlier" last.
      const ordered = Array.from(groups.values());
      ordered.sort((a, b) => {
        if (a.iso === 'earlier') return 1;
        if (b.iso === 'earlier') return -1;
        return a.iso < b.iso ? 1 : -1;
      });
      return ordered;
    }
  };

  installFeedState(obj, isAdmin);
  installFeedSse(obj);
  installFeedActions(obj);
  installFeedRender(obj);
  installFeedDiscovery(obj);
  installFeedTriage(obj);
  // Mixin: emoji reactions + reply, wired to the polymorphic social API.
  installFeedSocial(obj);
  return obj;
}
