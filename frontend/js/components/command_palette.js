/**
 * Cmd+K command palette + global keyboard shortcuts.
 *
 * The Alpine factory ``commandPalette()`` is wired via
 * ``bootstrap.js`` (which re-attaches it to ``window`` so the
 * partial's ``x-data="commandPalette()"`` keeps working unchanged).
 *
 * The palette owns four user-facing surfaces:
 *
 * * Cmd-K (or Ctrl-K) — open the search palette anywhere, including
 *   while focus is in an input.
 * * ``?`` — toggle the keyboard-shortcuts help dialog.
 * * Vim-style ``g`` chord — ``gh`` / ``gj`` / ``gd`` / ``gs`` /
 *   ``gq`` route to home / jobs / dashboards / SQL editor / query
 *   history with a 1-second timeout.
 * * ``r`` — reload the current page through the toast helper, but
 *   only when ``<body data-pql-refresh="1">`` opts in (list pages).
 */

const RECENT_KEY = 'pql.recentSearches';
const RECENT_MAX = 10;
const DEBOUNCE_MS = 150;
const CHORD_TIMEOUT_MS = 1000;
const CHORD_ROUTES = {
  h: '/',
  j: '/jobs',
  d: '/dashboards',
  s: '/sql',
  q: '/queries',
};

function isMac() {
  return /Mac|iPhone|iPad/.test(navigator.platform);
}

function isEditableTarget(el) {
  if (!el) return false;
  const tag = el.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (el.isContentEditable) return true;
  return false;
}

function loadRecent() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, RECENT_MAX) : [];
  } catch (e) {
    return [];
  }
}

function saveRecent(list) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX)));
  } catch (e) {
    /* quota / disabled storage — ignore */
  }
}

export function commandPalette() {
  const mod = isMac() ? '⌘' : 'Ctrl';
  return {
    open: false,
    helpOpen: false,
    query: '',
    results: [],
    selected: 0,
    recent: [],
    loading: false,
    modKey: mod,
    shortcuts: [
      { keys: [mod, 'K'], combiner: '+', label: 'Open command palette' },
      { keys: ['?'], combiner: '', label: 'Show this help' },
      { keys: ['esc'], combiner: '', label: 'Close any modal' },
      { keys: ['↑', '↓'], combiner: ' ', label: 'Move selection in palette' },
      { keys: ['↵'], combiner: '', label: 'Open the selected hit' },
      { keys: ['g', 'h'], combiner: ' ', label: 'Go to home' },
      { keys: ['g', 'j'], combiner: ' ', label: 'Go to jobs' },
      { keys: ['g', 'd'], combiner: ' ', label: 'Go to dashboards' },
      { keys: ['g', 's'], combiner: ' ', label: 'Go to SQL editor' },
      { keys: ['g', 'q'], combiner: ' ', label: 'Go to query history' },
      { keys: ['r'], combiner: '', label: 'Refresh current list' },
      // Page-specific shortcuts — only fire on the matching surface.
      { keys: [mod, 'S'], combiner: '+', label: 'Save (notebook editor)' },
      { keys: ['c'], combiner: '', label: 'Toggle preview (SQL editor)' },
    ],
    _debounceTimer: null,
    _seq: 0,
    _chordTimer: null,
    _chordPending: false,

    init() {
      this.recent = loadRecent();
      // bootstrap.Modal owns the backdrop, scroll-lock, focus-trap and
      // return-focus; Alpine owns the search content and ↑↓↵ navigation.
      // Show/hide is driven through these instances; the bs events keep
      // the Alpine flags in sync when the modal closes via Esc/backdrop.
      this._modal = window.bootstrap.Modal.getOrCreateInstance(this.$refs.modal);
      this._help = window.bootstrap.Modal.getOrCreateInstance(this.$refs.helpModal);
      this.$refs.modal.addEventListener('shown.bs.modal', () => {
        if (this.$refs.search) this.$refs.search.focus();
      });
      this.$refs.modal.addEventListener('hidden.bs.modal', () => {
        this._resetPalette();
        this._sweepBackdrops();
      });
      this.$refs.helpModal.addEventListener('hidden.bs.modal', () => {
        this.helpOpen = false;
        this._sweepBackdrops();
      });
      // wire the footer-bar "Show keyboard shortcuts" button (it
      // dispatches ``pql:show-shortcuts``) to the help modal.
      window.addEventListener('pql:show-shortcuts', () => this.openHelp());
    },

    openPalette() {
      if (this.open) return;
      // Never run two modal transitions at once — showing one modal
      // while another is still animating out orphans a Bootstrap
      // backdrop. If the help modal is up, just close it; a second
      // Cmd-K then opens the palette cleanly.
      if (this.helpOpen) {
        this._help.hide();
        this._scheduleSweep();
        return;
      }
      this.open = true;
      this.query = '';
      this.results = [];
      this.selected = 0;
      // focus lands on shown.bs.modal, after the focus-trap is armed.
      this._modal.show();
    },

    closePalette() {
      // hide() fires hidden.bs.modal → _resetPalette(); the guard keeps
      // closing working if the modal instance failed to construct.
      if (this._modal) this._modal.hide();
      else this._resetPalette();
      this._scheduleSweep();
    },

    _resetPalette() {
      this.open = false;
      this.query = '';
      this.results = [];
      this.loading = false;
      if (this._debounceTimer) {
        clearTimeout(this._debounceTimer);
        this._debounceTimer = null;
      }
    },

    // Safety net: once a modal has fully closed and none is shown,
    // strip any backdrop / scroll-lock Bootstrap may have orphaned, so
    // the page can never end up permanently dimmed or unclickable.
    _sweepBackdrops() {
      if (document.querySelector('.modal.show')) return;
      document.querySelectorAll('.modal-backdrop').forEach((b) => {
        b.remove();
      });
      document.body.classList.remove('modal-open');
      document.body.style.removeProperty('overflow');
      document.body.style.removeProperty('padding-right');
    },

    // hidden.bs.modal sweeps immediately, but if a modal is hidden while
    // it is still animating in, Bootstrap may never emit that event and
    // leaves the backdrop behind. Schedule a fallback sweep after the
    // transition window so a fast Esc/toggle can't strand a backdrop.
    _scheduleSweep() {
      if (this._sweepTimer) clearTimeout(this._sweepTimer);
      this._sweepTimer = setTimeout(() => this._sweepBackdrops(), 300);
    },

    openHelp() {
      this.helpOpen = true;
      this._help.show();
    },

    toggleHelp() {
      if (this.helpOpen) {
        this._help.hide();
        this._scheduleSweep();
      } else {
        this.openHelp();
      }
    },

    onGlobalKeydown(e) {
      // Cmd+K / Ctrl+K — toggles palette from anywhere, including inputs
      const isK = e.key === 'k' || e.key === 'K';
      if (isK && (e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
        e.preventDefault();
        this._cancelChord();
        if (this.open) this.closePalette();
        else this.openPalette();
        return;
      }
      // Escape on either modal is handled by bootstrap.Modal's own
      // keyboard binding (which also restores focus to the trigger).
      // The remaining unmodified single-key bindings never fire
      // while a modal is open or the user is typing.
      if (this.open || this.helpOpen) return;
      if (isEditableTarget(e.target)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      // A page-level handler may already own this key (e.g. the feed's
      // own ``?`` shortcuts help); if it claimed the event, don't also
      // fire the global binding and stack a second modal on top.
      if (e.defaultPrevented) return;

      // ? opens the global shortcuts help.
      if (e.key === '?') {
        e.preventDefault();
        this._cancelChord();
        this.toggleHelp();
        return;
      }

      // r — refresh the current list page (opt-in via <body data-pql-refresh>)
      if (e.key === 'r' && document.body.dataset.pqlRefresh === '1') {
        e.preventDefault();
        this._cancelChord();
        window.pqlApi.reloadWithToast('Refreshing.', { delay: 0 });
        return;
      }

      // Vim-style chord: `g` then {h,j,d} within 1s
      if (this._chordPending) {
        const target = CHORD_ROUTES[e.key];
        this._cancelChord();
        if (target) {
          e.preventDefault();
          window.location.href = target;
        }
        return;
      }
      if (e.key === 'g') {
        e.preventDefault();
        this._chordPending = true;
        this._chordTimer = setTimeout(() => this._cancelChord(), CHORD_TIMEOUT_MS);
      }
    },

    _cancelChord() {
      this._chordPending = false;
      if (this._chordTimer) {
        clearTimeout(this._chordTimer);
        this._chordTimer = null;
      }
    },

    onDialogKeydown(e) {
      const list = this.query ? this.results : this.recent;
      // Escape is handled by bootstrap.Modal; here we only own list nav.
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (list.length === 0) return;
        this.selected = (this.selected + 1) % list.length;
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (list.length === 0) return;
        this.selected = (this.selected - 1 + list.length) % list.length;
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (list.length === 0) return;
        this.select(this.selected);
      }
    },

    onQueryInput() {
      this.selected = 0;
      if (this._debounceTimer) clearTimeout(this._debounceTimer);
      if (!this.query.trim()) {
        this.results = [];
        this.loading = false;
        return;
      }
      this._debounceTimer = setTimeout(() => this.fetchResults(), DEBOUNCE_MS);
    },

    async fetchResults() {
      const q = this.query.trim();
      if (!q) {
        this.results = [];
        return;
      }
      this.loading = true;
      const seq = ++this._seq;
      try {
        const url = '/api/search?q=' + encodeURIComponent(q) + '&limit=50';
        const res = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (seq !== this._seq) return; // stale response, ignore
        this.results = Array.isArray(data) ? data : [];
        this.selected = 0;
      } catch (e) {
        if (seq !== this._seq) return;
        this.results = [];
        if (window.pqlToast) window.pqlToast.error('Search failed: ' + e.message);
      } finally {
        if (seq === this._seq) this.loading = false;
      }
    },

    select(idx) {
      const list = this.query ? this.results : this.recent;
      const hit = list[idx];
      if (!hit || !hit.url) return;
      this.pushRecent(hit);
      this.closePalette();
      window.location.href = hit.url;
    },

    pushRecent(hit) {
      const entry = {
        type: hit.type,
        label: hit.label,
        description: hit.description || '',
        url: hit.url,
      };
      const next = [entry]
        .concat(this.recent.filter((r) => r.url !== entry.url))
        .slice(0, RECENT_MAX);
      this.recent = next;
      saveRecent(next);
    },
  };
}
