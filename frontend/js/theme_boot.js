// Theme boot — Bootstrap 5.3 color-modes init, shared by every layout
// (base.html, base_public.html, _layouts/auth_chromeless.html).
//
// Loaded as a CLASSIC, render-blocking script in <head> BEFORE the
// first stylesheet so ``data-bs-theme`` is correct when CSS parses —
// no theme flash on first paint (scripts/check-theme-boot-order.sh
// enforces the ordering).  Default ``auto`` follows
// ``prefers-color-scheme``; explicit picks persist in localStorage.
(function () {
  try {
    const stored = localStorage.getItem('pql.theme');
    const choice = stored || 'auto';
    const resolved =
      choice === 'auto'
        ? window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light'
        : choice;
    document.documentElement.setAttribute('data-bs-theme', resolved);
    document.documentElement.setAttribute('data-pql-theme-choice', choice);
  } catch (_e) {
    // localStorage disabled (private mode etc.) — fall back to the
    // static ``dark`` attribute on <html>.
  }
})();

// Delegated theme-cycle handler (auto → light → dark → auto) for any
// button carrying ``data-pql-theme-cycle`` — replaces the inline
// onclick the public topbar used to carry.
document.addEventListener('click', (event) => {
  const btn = event.target.closest('[data-pql-theme-cycle]');
  if (!btn) return;
  const root = document.documentElement;
  const current = root.getAttribute('data-pql-theme-choice') || 'auto';
  const next = current === 'auto' ? 'light' : current === 'light' ? 'dark' : 'auto';
  try {
    localStorage.setItem('pql.theme', next);
  } catch (_e) {}
  const resolved =
    next === 'auto'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      : next;
  root.setAttribute('data-bs-theme', resolved);
  root.setAttribute('data-pql-theme-choice', next);
  btn.title = `Theme: ${next}`;
});
