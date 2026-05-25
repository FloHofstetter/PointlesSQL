// keyboard navigation for multi-select list pages.
//
// Gmail-style row shortcuts:
//   j / ArrowDown   — next row (highlights, scrolls into view)
//   k / ArrowUp     — previous row
//   x               — toggle selection on the focused row
//   Shift+x         — range-select from last selection anchor to focus
//   Esc             — clear selection
//   Enter           — open the focused row's primary link
//
// Activates on any page that contains a table tagged with
// ``data-pql-keynav-table="1"``.  The table's
// ``tr`` rows must contain at least one checkbox in any
// ``input[type=checkbox]`` cell (the bulk-select pattern);
// the script clicks that checkbox so the Alpine scope picks
// up the change.
//
// Ignores key events when the focus is inside an editable field
// (input/textarea/contenteditable) so typing in filters / forms
// never accidentally selects rows.

(() => {
  function shouldIgnore(ev) {
    const t = ev.target;
    if (!t) return false;
    const tag = t.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      // Exception: checkboxes are inert for typing — let shortcuts pass.
      if (tag === 'INPUT' && t.type === 'checkbox') return false;
      return true;
    }
    if (t.isContentEditable) return true;
    return false;
  }

  function rowsIn(table) {
    return Array.from(table.querySelectorAll('tbody tr')).filter((tr) => tr.offsetParent !== null);
  }

  function focusRow(rows, idx) {
    rows.forEach((r) => {
      r.removeAttribute('data-pql-keynav-focus');
    });
    if (idx < 0 || idx >= rows.length) return -1;
    const r = rows[idx];
    r.setAttribute('data-pql-keynav-focus', '1');
    r.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    return idx;
  }

  function clickCheckbox(row) {
    const cb = row.querySelector('input[type="checkbox"]');
    if (cb) cb.click();
  }

  function clickRowLink(row) {
    const link = row.querySelector('a[href]');
    if (link) link.click();
  }

  function rangeSelect(rows, anchor, focus) {
    const lo = Math.min(anchor, focus);
    const hi = Math.max(anchor, focus);
    for (let i = lo; i <= hi; i++) {
      const cb = rows[i].querySelector('input[type="checkbox"]');
      if (cb && !cb.checked) cb.click();
    }
  }

  function init() {
    const table = document.querySelector('[data-pql-keynav-table="1"]');
    if (!table) return;

    let focusIdx = -1;
    let anchorIdx = -1;

    function refreshRows() {
      return rowsIn(table);
    }

    document.addEventListener('keydown', (ev) => {
      if (shouldIgnore(ev)) return;
      const rows = refreshRows();
      if (!rows.length) return;

      switch (ev.key) {
        case 'j':
        case 'ArrowDown':
          ev.preventDefault();
          focusIdx = focusRow(rows, Math.min(rows.length - 1, focusIdx < 0 ? 0 : focusIdx + 1));
          break;
        case 'k':
        case 'ArrowUp':
          ev.preventDefault();
          focusIdx = focusRow(rows, Math.max(0, focusIdx < 0 ? 0 : focusIdx - 1));
          break;
        case 'x':
        case 'X':
          if (focusIdx < 0) return;
          ev.preventDefault();
          if (ev.shiftKey && anchorIdx >= 0) {
            rangeSelect(rows, anchorIdx, focusIdx);
          } else {
            clickCheckbox(rows[focusIdx]);
            anchorIdx = focusIdx;
          }
          break;
        case 'Escape': {
          if (focusIdx < 0) return;
          ev.preventDefault();
          // Clear via the page's own clearSelection() if exposed;
          // otherwise un-tick every checkbox manually.
          const wrapper = table.closest('[x-data]');
          const scope = wrapper && wrapper._x_dataStack && wrapper._x_dataStack[0];
          if (scope && typeof scope.clearSelection === 'function') {
            scope.clearSelection();
          } else {
            rows.forEach((r) => {
              const cb = r.querySelector('input[type="checkbox"]:checked');
              if (cb) cb.click();
            });
          }
          anchorIdx = -1;
          break;
        }
        case 'Enter':
          if (focusIdx < 0) return;
          ev.preventDefault();
          clickRowLink(rows[focusIdx]);
          break;
        default:
          return;
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
  // Re-init on HTMX swap of #main-content (boost navigations).
  document.body.addEventListener('htmx:afterSwap', (ev) => {
    if (ev.target && ev.target.id === 'main-content') init();
  });
})();
