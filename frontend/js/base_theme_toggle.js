/**
 * Theme color-mode dropdown click-handler + auto-mode reactor.
 *
 * Side-effect module. The synchronous head-block in base.html already
 * applied the correct ``data-bs-theme`` before paint (FOUC-critical
 * path). This listener handles user clicks on the topbar dropdown,
 * syncs the trigger icon, and re-applies on OS prefer-changes when
 * the user is in ``auto`` mode.
 *
 * Imported once from ``bootstrap.js``.
 */

(() => {
  const root = document.documentElement;
  function resolved(choice) {
    return choice === 'auto'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      : choice;
  }
  function syncIcon(choice) {
    const icon = document.querySelector('[data-pql-theme-icon]');
    if (!icon) return;
    icon.classList.remove('bi-sun-fill', 'bi-moon-stars-fill', 'bi-circle-half');
    icon.classList.add(
      choice === 'light'
        ? 'bi-sun-fill'
        : choice === 'dark'
          ? 'bi-moon-stars-fill'
          : 'bi-circle-half'
    );
  }
  function syncCheck(choice) {
    document.querySelectorAll('.pql-theme-option').forEach((btn) => {
      btn.classList.toggle(
        'pql-theme-option--active',
        btn.getAttribute('data-bs-theme-value') === choice
      );
    });
  }
  function apply(choice) {
    root.setAttribute('data-bs-theme', resolved(choice));
    root.setAttribute('data-pql-theme-choice', choice);
    try {
      localStorage.setItem('pql.theme', choice);
    } catch (e) {
      /* quota / disabled */
    }
    syncIcon(choice);
    syncCheck(choice);
  }
  document.body.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-bs-theme-value]');
    if (!btn) return;
    apply(btn.getAttribute('data-bs-theme-value'));
  });
  syncIcon(root.getAttribute('data-pql-theme-choice') || 'auto');
  syncCheck(root.getAttribute('data-pql-theme-choice') || 'auto');
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if ((root.getAttribute('data-pql-theme-choice') || 'auto') === 'auto') {
      root.setAttribute('data-bs-theme', resolved('auto'));
    }
  });
})();
