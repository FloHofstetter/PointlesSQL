// Per-entity ⋯-action menu handler.
//
// Single document-level click listener that handles every
// ``.pql-entity-mute-btn`` rendered by ``_macros/entity_actions.html``.
// The Copy-link / Copy-citation items reuse the existing
// ``.pql-copy-btn`` delegated handler from ``copy_button.js`` — only
// the mute action needs a server hop, so it's the only handler we
// register here.

import { pqlApi } from './api.js';

function setupEntityActions() {
  document.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('.pql-entity-mute-btn');
    if (!btn) return;
    ev.preventDefault();
    const kind = btn.dataset.pqlMuteKind;
    const ref = btn.dataset.pqlMuteRef;
    const label = btn.dataset.pqlMuteLabel || `${kind} ${ref}`;
    if (!kind || !ref) return;
    const res = await pqlApi.fetch('/api/feed/mute', {
      method: 'POST',
      body: { entity_kind: kind, entity_ref: ref },
      silent: true,
    });
    if (res.ok) {
      window.pqlToast?.success?.(`Muted ${label}.`);
    } else {
      window.pqlToast?.error?.(`Mute failed: ${res.error || 'unknown error'}`);
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setupEntityActions);
} else {
  setupEntityActions();
}

export { setupEntityActions };
