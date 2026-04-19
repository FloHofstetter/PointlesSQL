// Phase 12.7 Sprint 74 — editor settings drawer.
//
// Three knobs (theme, font-size, autosave-debounce-ms) persisted to
// localStorage and applied via a ``pql:settings-changed`` CustomEvent
// the per-tab editors listen for in main.js.  Theme changes are
// page-global (Monaco's setTheme is process-global across all
// editors); font-size + debounce are per-instance and the broadcast
// lets every open tab pick them up without a reload.
//
// Closure-state invariant: the singleton drawer DOM node lives in
// module scope here, never on Alpine's reactive proxy.

const STORAGE_THEME = 'pql.nbedit.theme.v1';
const STORAGE_FONT = 'pql.nbedit.fontSize.v1';
const STORAGE_DEBOUNCE = 'pql.nbedit.autosave.debounceMs.v1';

const DEFAULT_THEME = 'vs-dark';
const DEFAULT_FONT = 13;
const DEFAULT_DEBOUNCE = 1500;

const THEMES = [
    { id: 'vs-dark', label: 'Dark (vs-dark)' },
    { id: 'vs', label: 'Light (vs)' },
    { id: 'hc-black', label: 'High contrast (hc-black)' },
];

const FONT_MIN = 10;
const FONT_MAX = 22;
const DEBOUNCE_MIN = 200;
const DEBOUNCE_MAX = 2000;

let _offcanvasEl = null;
let _bsOffcanvas = null;

function readJSONNumber(key, fallback, min, max) {
    try {
        const raw = window.localStorage.getItem(key);
        if (raw === null) return fallback;
        const n = parseInt(JSON.parse(raw), 10);
        if (!Number.isFinite(n)) return fallback;
        return Math.max(min, Math.min(max, n));
    } catch {
        return fallback;
    }
}

function readJSONString(key, fallback, allowed) {
    try {
        const raw = window.localStorage.getItem(key);
        if (raw === null) return fallback;
        const v = String(JSON.parse(raw));
        return allowed.includes(v) ? v : fallback;
    } catch {
        return fallback;
    }
}

export function loadSettings() {
    return {
        theme: readJSONString(STORAGE_THEME, DEFAULT_THEME, THEMES.map(t => t.id)),
        fontSize: readJSONNumber(STORAGE_FONT, DEFAULT_FONT, FONT_MIN, FONT_MAX),
        debounceMs: readJSONNumber(STORAGE_DEBOUNCE, DEFAULT_DEBOUNCE, DEBOUNCE_MIN, DEBOUNCE_MAX),
    };
}

function persist(key, value) {
    try {
        window.localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
        console.warn('[settings_drawer] localStorage write failed', e);
    }
}

function broadcast(settings) {
    document.dispatchEvent(new CustomEvent('pql:settings-changed', { detail: settings }));
}

function buildOffcanvas() {
    const root = document.createElement('div');
    root.className = 'offcanvas offcanvas-end pql-nbedit-settings-drawer';
    root.tabIndex = -1;
    root.setAttribute('aria-labelledby', 'pql-nbedit-settings-title');
    root.innerHTML = `
        <div class="offcanvas-header">
          <h5 class="offcanvas-title" id="pql-nbedit-settings-title">Editor settings</h5>
          <button type="button" class="btn-close" data-bs-dismiss="offcanvas" aria-label="Close"></button>
        </div>
        <div class="offcanvas-body">
          <div class="mb-3">
            <label for="pql-nbedit-settings-theme" class="form-label">Theme</label>
            <select id="pql-nbedit-settings-theme" class="form-select form-select-sm">
              ${THEMES.map(t => `<option value="${t.id}">${t.label}</option>`).join('')}
            </select>
            <div class="form-text">Theme is page-global — affects every open tab's editor.</div>
          </div>
          <div class="mb-3">
            <label for="pql-nbedit-settings-font" class="form-label">Font size</label>
            <input id="pql-nbedit-settings-font" type="number" min="${FONT_MIN}" max="${FONT_MAX}" step="1"
                   class="form-control form-control-sm" />
            <div class="form-text">Per-editor pixel size for Monaco (${FONT_MIN}-${FONT_MAX}px).</div>
          </div>
          <div class="mb-3">
            <label for="pql-nbedit-settings-debounce" class="form-label">Autosave debounce</label>
            <input id="pql-nbedit-settings-debounce" type="number" min="${DEBOUNCE_MIN}" max="${DEBOUNCE_MAX}" step="100"
                   class="form-control form-control-sm" />
            <div class="form-text">Milliseconds between last keystroke and POST /api/notebook/doc.</div>
          </div>
        </div>
    `;
    return root;
}

export function mountSettingsDrawer() {
    if (_offcanvasEl) return;
    const settings = loadSettings();
    _offcanvasEl = buildOffcanvas();
    document.body.appendChild(_offcanvasEl);

    const themeEl = _offcanvasEl.querySelector('#pql-nbedit-settings-theme');
    const fontEl = _offcanvasEl.querySelector('#pql-nbedit-settings-font');
    const debEl = _offcanvasEl.querySelector('#pql-nbedit-settings-debounce');

    themeEl.value = settings.theme;
    fontEl.value = String(settings.fontSize);
    debEl.value = String(settings.debounceMs);

    themeEl.addEventListener('change', () => {
        const v = themeEl.value;
        if (!THEMES.some(t => t.id === v)) return;
        persist(STORAGE_THEME, v);
        broadcast(loadSettings());
    });
    fontEl.addEventListener('change', () => {
        let n = parseInt(fontEl.value, 10);
        if (!Number.isFinite(n)) n = DEFAULT_FONT;
        n = Math.max(FONT_MIN, Math.min(FONT_MAX, n));
        fontEl.value = String(n);
        persist(STORAGE_FONT, n);
        broadcast(loadSettings());
    });
    debEl.addEventListener('change', () => {
        let n = parseInt(debEl.value, 10);
        if (!Number.isFinite(n)) n = DEFAULT_DEBOUNCE;
        n = Math.max(DEBOUNCE_MIN, Math.min(DEBOUNCE_MAX, n));
        debEl.value = String(n);
        persist(STORAGE_DEBOUNCE, n);
        broadcast(loadSettings());
    });
}

export function openSettingsDrawer() {
    if (!_offcanvasEl) mountSettingsDrawer();
    if (!window.bootstrap || !window.bootstrap.Offcanvas) {
        // Fallback: just toggle the .show class so the drawer is at
        // least visible without Bootstrap's JS — used in test envs.
        _offcanvasEl.classList.add('show');
        return;
    }
    if (!_bsOffcanvas) {
        _bsOffcanvas = new window.bootstrap.Offcanvas(_offcanvasEl);
    }
    _bsOffcanvas.show();
}
