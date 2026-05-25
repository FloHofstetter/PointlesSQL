// promise-based confirm helper.
//
// Replaces `window.confirm()` (bare browser dialog, no branding) with
// a Bootstrap modal whose markup lives in
// `templates/components/confirm_modal.html`.  Returns a Promise that
// resolves to `true` on OK and `false` on Cancel / dismiss.
//
// Usage:
//   if (!await window.pqlConfirm('Delete alert?', 'This cannot be undone.')) return;
//   // ... destructive action
//
// Optional `opts`:
//   - confirmLabel: button label override (default "Delete")
//   - confirmClass: button class override (default "btn-danger")
(() => {
  function pqlConfirm(title, body, opts) {
    opts = opts || {};
    const modalEl = document.getElementById('pql-confirm-modal');
    if (!modalEl || !window.bootstrap) {
      // Fall back to native confirm if Bootstrap / modal markup
      // is missing (anonymous pages, etc).  Keeps callers safe.
      return Promise.resolve(window.confirm(title + '\n\n' + (body || '')));
    }

    const titleEl = document.getElementById('pql-confirm-title');
    const bodyEl = document.getElementById('pql-confirm-body');
    const okBtn = document.getElementById('pql-confirm-ok');

    if (titleEl) titleEl.textContent = title || 'Confirm';
    if (bodyEl) bodyEl.textContent = body || '';

    if (okBtn) {
      okBtn.textContent = opts.confirmLabel || 'Delete';
      okBtn.className = 'btn ' + (opts.confirmClass || 'btn-danger');
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    return new Promise((resolve) => {
      let decided = false;

      function onOk() {
        decided = true;
        cleanup();
        modal.hide();
        resolve(true);
      }
      function onHidden() {
        cleanup();
        if (!decided) resolve(false);
      }
      function cleanup() {
        if (okBtn) okBtn.removeEventListener('click', onOk);
        modalEl.removeEventListener('hidden.bs.modal', onHidden);
      }
      if (okBtn) okBtn.addEventListener('click', onOk);
      modalEl.addEventListener('hidden.bs.modal', onHidden);
      modal.show();
    });
  }

  window.pqlConfirm = pqlConfirm;
})();
