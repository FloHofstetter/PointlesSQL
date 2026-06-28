// CDF-tail admin page form shims (classic script via extra_js).
//
// Tiny shim: convert <form method="post"> + <input name="_method"
// value="DELETE"> pairs into actual fetch DELETE calls, then reload.
// Pattern matches what admin_audit_sinks.html does for non-GET HTML
// form deletes.
document.addEventListener('submit', (ev) => {
  const form = ev.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (!form.hasAttribute('data-cdf-tail-delete-form')) return;
  const methodInput = form.querySelector('input[name="_method"]');
  if (!methodInput || methodInput.value.toUpperCase() !== 'DELETE') return;
  ev.preventDefault();
  fetch(form.action, { method: 'DELETE', credentials: 'same-origin' })
    .then((r) => {
      if (r.ok) {
        window.location.reload();
      } else {
        r.text().then((t) => {
          window.pqlToast?.error?.(`Delete failed: ${t || r.status}`);
        });
      }
    })
    .catch((err) => {
      window.pqlToast?.error?.(`Delete failed: ${err}`);
    });
});

// Convert the create-form POST to JSON so the existing
// /api/admin/cdf-subscriptions body-parser (FastAPI Body(...))
// accepts it.
document.addEventListener('submit', (ev) => {
  const form = ev.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (!form.hasAttribute('data-cdf-tail-create-form')) return;
  ev.preventDefault();
  const fd = new FormData(form);
  const payload = {};
  fd.forEach((v, k) => {
    if (v) payload[k] = v;
  });
  fetch(form.action, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then((r) => {
      if (r.ok) {
        window.location.reload();
      } else {
        r.text().then((t) => {
          window.pqlToast?.error?.(`Create failed: ${t || r.status}`);
        });
      }
    })
    .catch((err) => {
      window.pqlToast?.error?.(`Create failed: ${err}`);
    });
});
