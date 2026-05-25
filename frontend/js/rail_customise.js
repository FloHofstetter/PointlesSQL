/*
 * per-user primary-rail customisation (localStorage MVP).
 *
 * The primary rail surfaces 23 entries across five IA
 * groups.  Some users (e.g. an auditor who never builds notebooks)
 * find the full surface noisy.  This module lets each device store a
 * list of hidden rail sections; the rail stays server-rendered (so
 * the markup is identical for everyone) and we toggle visibility on
 * the client.
 *
 * Why localStorage and not a server preference: the rail decision is
 * a per-device ergonomic preference, not an entitlement.  An auditor
 * on a borrowed kiosk should not push their hidden-list to the
 * server.  When (if) we add cross-device sync, the localStorage
 * shape stays the same; the server just becomes a secondary writer.
 *
 * Surface contract:
 *   - Each rail entry carries ``data-section="<key>"`` (already true
 *     for the htmx:afterSwap active-state sync in base.html).
 *   - Hidden sections are stored as a JSON array under the
 *     ``pql:rail-hidden`` localStorage key.
 *   - The parent ``<li>`` of each rail entry gets
 *     ``data-rail-hidden="1"`` when hidden; CSS in icon_rail.css does
 *     the actual ``display: none``.
 *   - The "Customise" offcanvas (rail_customise_offcanvas.html) is
 *     populated on the fly from the live rail DOM, so we never
 *     duplicate the entry list in two places.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'pql:rail-hidden';

  function getHidden() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return new Set();
      const parsed = JSON.parse(raw);
      return new Set(Array.isArray(parsed) ? parsed : []);
    } catch (e) {
      return new Set();
    }
  }

  function setHidden(hiddenSet) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...hiddenSet]));
    } catch (e) {
      // Quota-exceeded / private-mode fallback — silent.
    }
  }

  function applyHidden() {
    const hidden = getHidden();
    document.querySelectorAll('.pql-icon-rail__link[data-section]').forEach((link) => {
      const li = link.closest('li');
      if (!li) return;
      const section = link.dataset.section;
      if (section && hidden.has(section)) {
        li.setAttribute('data-rail-hidden', '1');
      } else {
        li.removeAttribute('data-rail-hidden');
      }
    });
  }

  function railEntryLabel(link) {
    const labelSpan = link.querySelector('.pql-icon-rail__label');
    if (labelSpan && labelSpan.textContent.trim()) {
      return labelSpan.textContent.trim();
    }
    return (
      link.getAttribute('aria-label') ||
      link.getAttribute('title') ||
      link.dataset.section ||
      'Untitled'
    ).trim();
  }

  function populateOffcanvas() {
    const list = document.getElementById('pql-rail-customise-list');
    if (!list) return;
    list.innerHTML = '';
    const hidden = getHidden();
    const links = document.querySelectorAll('.pql-icon-rail__link[data-section]');
    const seen = new Set();
    links.forEach((link) => {
      const section = link.dataset.section;
      if (!section || seen.has(section)) return;
      seen.add(section);
      const label = railEntryLabel(link);
      const row = document.createElement('label');
      row.className = 'd-flex align-items-center gap-2 py-1 mb-0';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'form-check-input';
      checkbox.dataset.railSection = section;
      checkbox.checked = !hidden.has(section);
      const text = document.createElement('span');
      text.textContent = label;
      row.appendChild(checkbox);
      row.appendChild(text);
      list.appendChild(row);
    });
  }

  function handleToggle(event) {
    const cb = event.target;
    if (!(cb instanceof HTMLInputElement)) return;
    if (!cb.matches('[data-rail-section]')) return;
    const section = cb.dataset.railSection;
    if (!section) return;
    const hidden = getHidden();
    if (cb.checked) {
      hidden.delete(section);
    } else {
      hidden.add(section);
    }
    setHidden(hidden);
    applyHidden();
  }

  function reset() {
    setHidden(new Set());
    applyHidden();
    populateOffcanvas();
  }

  function init() {
    applyHidden();
    const offcanvas = document.getElementById('pql-rail-customise-offcanvas');
    if (offcanvas) {
      offcanvas.addEventListener('show.bs.offcanvas', populateOffcanvas);
      const list = document.getElementById('pql-rail-customise-list');
      if (list) list.addEventListener('change', handleToggle);
      const resetBtn = document.getElementById('pql-rail-customise-reset');
      if (resetBtn) resetBtn.addEventListener('click', reset);
    }
    // Re-apply after HTMX boosts swap #main-content — the rail
    // lives outside #main-content so its DOM survives, but
    // belt-and-braces in case a future template moves it.
    document.body.addEventListener('htmx:afterSwap', applyHidden);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
