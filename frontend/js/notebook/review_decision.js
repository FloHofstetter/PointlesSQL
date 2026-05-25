/**
 * Per-cell review-decision vocabulary.
 *
 * Review decisions are encoded as a leading body_md line on a comment
 * carrying ``category='review'``.  The polymorphic comments table has
 * no dedicated decision column; adding one would be a migration for
 * what is effectively a UI affordance.  Keeping the decision in the
 * body keeps the round-trip stable (the JS extracts it back on render)
 * and degrades gracefully on older clients that just see a regular
 * review comment.
 *
 * Pure module: no `this`, no DOM, no fetch — only the enum + two
 * helpers that derive the decision from a body and strip the prefix
 * for display.
 */

export const REVIEW_DECISIONS = [
  {
    id: 'approved',
    label: 'Approved',
    icon: 'bi-check-circle-fill',
    className: 'text-success',
    prefix: '✅ **Approved**',
  },
  {
    id: 'changes_requested',
    label: 'Changes requested',
    icon: 'bi-exclamation-triangle-fill',
    className: 'text-warning',
    prefix: '⚠️ **Changes requested**',
  },
  {
    id: 'comment',
    label: 'Comment only',
    icon: 'bi-chat-left-text',
    className: 'text-muted',
    prefix: '💬 **Reviewed**',
  },
];

export function extractReviewDecision(body_md) {
  const head = (body_md || '').split('\n')[0].trim();
  for (const d of REVIEW_DECISIONS) {
    if (head === d.prefix) return d;
  }
  return REVIEW_DECISIONS[2];
}

export function bodyWithoutPrefix(body_md) {
  const d = extractReviewDecision(body_md);
  const body = body_md || '';
  if (body.startsWith(d.prefix)) {
    return body.slice(d.prefix.length).replace(/^\n+/, '');
  }
  return body;
}
