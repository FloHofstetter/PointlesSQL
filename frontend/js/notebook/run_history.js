// Phase 12.7 Sprint 73 — per-cell run-history popover + source diff.
//
// One module-scoped popover at a time.  ``mountHistoryButton`` adds
// a clock-icon ``History`` button to a cell's toolbar; click →
// ``openPopover`` fetches /api/notebook/cell-runs?path=…&content_hash=…
// and renders the last N rows (newest-first) with status pills,
// ``view diff`` toggles that render a jsdiff-based table comparing
// the historical source to the current Monaco buffer, and a
// ``re-run`` button that replays the historical source straight to
// the kernel WITHOUT modifying the Monaco buffer ("what did the
// old version produce?" UX).
//
// Closure-state invariant (Sprint 65 / BUG-64-02): the popover DOM
// node, in-flight AbortController, and per-cell history cache live
// in module scope here — never assigned to the caller's Alpine
// reactive proxy.  The grep gate at scripts/check-frontend-no-
// reactive-monaco.sh blocks ``this._historyCache`` /
// ``this._historyPopover`` / ``this._historyAbort`` to keep future
// edits honest.

const _historyCache = new Map();
let _popoverEl = null;
let _popoverAnchor = null;
let _inflightAbort = null;
let _outsideClickHandler = null;
let _escHandler = null;
const DIFF_LINE_CAP = 10000;

function fmtTime(iso) {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const mi = String(d.getMinutes()).padStart(2, '0');
        const ss = String(d.getSeconds()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
    } catch {
        return iso;
    }
}

function fmtDuration(startIso, endIso) {
    if (!startIso || !endIso) return '';
    try {
        const ms = Date.parse(endIso) - Date.parse(startIso);
        if (!Number.isFinite(ms) || ms < 0) return '';
        if (ms < 1000) return `${ms}ms`;
        const s = ms / 1000;
        if (s < 10) return `${s.toFixed(2)}s`;
        if (s < 60) return `${s.toFixed(1)}s`;
        return `${Math.floor(s / 60)}m${String(Math.floor(s % 60)).padStart(2, '0')}s`;
    } catch {
        return '';
    }
}

function renderDiffTable(oldSource, newSource) {
    const wrap = document.createElement('div');
    wrap.className = 'pql-nbedit-history-diff';
    const Diff = window.Diff;
    if (!Diff || typeof Diff.diffLines !== 'function') {
        wrap.textContent = 'Diff library unavailable — run scripts/vendor-diff-lib.sh.';
        return wrap;
    }
    // Cap diff input to keep O(N²) cost bounded.
    const oldLineCount = (oldSource || '').split('\n').length;
    const newLineCount = (newSource || '').split('\n').length;
    if (oldLineCount + newLineCount > DIFF_LINE_CAP) {
        wrap.textContent = `Diff too large (${oldLineCount + newLineCount} lines > ${DIFF_LINE_CAP}).`;
        return wrap;
    }
    const parts = Diff.diffLines(oldSource || '', newSource || '');
    const table = document.createElement('table');
    table.className = 'pql-nbedit-diff';
    let any = false;
    for (const part of parts) {
        const sign = part.added ? '+' : (part.removed ? '-' : ' ');
        const cls = part.added
            ? 'pql-nbedit-diff-add'
            : (part.removed ? 'pql-nbedit-diff-del' : 'pql-nbedit-diff-ctx');
        const lines = (part.value || '').split('\n');
        // Drop the trailing empty after the final newline so we don't
        // emit a phantom row per part.
        if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
        for (const line of lines) {
            any = true;
            const tr = document.createElement('tr');
            tr.className = cls;
            const sCell = document.createElement('td');
            sCell.className = 'pql-nbedit-diff-sign';
            sCell.textContent = sign;
            tr.appendChild(sCell);
            const lCell = document.createElement('td');
            lCell.className = 'pql-nbedit-diff-line';
            lCell.textContent = line;
            tr.appendChild(lCell);
            table.appendChild(tr);
        }
    }
    if (!any) {
        wrap.textContent = '(sources are identical)';
        return wrap;
    }
    wrap.appendChild(table);
    return wrap;
}

function renderRunRow(run, currentSource, onRerun) {
    const row = document.createElement('div');
    row.className = 'pql-nbedit-history-row';

    const head = document.createElement('div');
    head.className = 'pql-nbedit-history-head';

    const stamp = document.createElement('span');
    stamp.className = 'pql-nbedit-history-stamp';
    stamp.textContent = fmtTime(run.started_at);
    head.appendChild(stamp);

    const dur = document.createElement('span');
    dur.className = 'pql-nbedit-history-dur';
    dur.textContent = fmtDuration(run.started_at, run.finished_at);
    head.appendChild(dur);

    const pill = document.createElement('span');
    pill.className = `pql-nbedit-status-pill pql-nbedit-status-${run.status || 'idle'}`;
    pill.textContent = run.status || '?';
    head.appendChild(pill);

    if (run.execution_count != null) {
        const ec = document.createElement('span');
        ec.className = 'pql-nbedit-exec-count';
        ec.textContent = `[${run.execution_count}]`;
        head.appendChild(ec);
    }

    const diffBtn = document.createElement('button');
    diffBtn.type = 'button';
    diffBtn.className = 'btn btn-sm btn-outline-secondary pql-nbedit-history-diff-btn';
    diffBtn.textContent = 'view diff';
    diffBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        ev.preventDefault();
        const existing = row.querySelector('.pql-nbedit-history-diff');
        if (existing) {
            existing.remove();
            diffBtn.textContent = 'view diff';
            return;
        }
        const diff = renderDiffTable(run.source, currentSource);
        row.appendChild(diff);
        diffBtn.textContent = 'hide diff';
    });
    head.appendChild(diffBtn);

    const rerunBtn = document.createElement('button');
    rerunBtn.type = 'button';
    rerunBtn.className = 'btn btn-sm btn-outline-primary pql-nbedit-history-rerun-btn';
    rerunBtn.textContent = 're-run';
    rerunBtn.title = 'Re-execute this historical source (does NOT modify the cell)';
    rerunBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        ev.preventDefault();
        if (typeof onRerun === 'function') onRerun(run.source);
        closePopover();
    });
    head.appendChild(rerunBtn);

    row.appendChild(head);
    return row;
}

function ensurePopover() {
    if (_popoverEl) return _popoverEl;
    const el = document.createElement('div');
    el.className = 'pql-nbedit-history-popover';
    el.style.position = 'absolute';
    el.style.zIndex = '1080';
    document.body.appendChild(el);
    _popoverEl = el;
    return el;
}

function positionPopover(anchorEl) {
    if (!_popoverEl || !anchorEl) return;
    const rect = anchorEl.getBoundingClientRect();
    const top = window.scrollY + rect.bottom + 4;
    const left = Math.max(8, window.scrollX + rect.right - 480);
    _popoverEl.style.top = `${top}px`;
    _popoverEl.style.left = `${left}px`;
    _popoverEl.style.width = '480px';
    _popoverEl.style.maxHeight = '60vh';
    _popoverEl.style.overflowY = 'auto';
}

export function closePopover() {
    if (_popoverEl) {
        _popoverEl.remove();
        _popoverEl = null;
    }
    _popoverAnchor = null;
    if (_inflightAbort) {
        try { _inflightAbort.abort(); } catch {}
        _inflightAbort = null;
    }
    if (_outsideClickHandler) {
        document.removeEventListener('mousedown', _outsideClickHandler, true);
        _outsideClickHandler = null;
    }
    if (_escHandler) {
        document.removeEventListener('keydown', _escHandler, true);
        _escHandler = null;
    }
}

export async function openPopover({ path, contentHash, anchorEl, currentSource, onRerun }) {
    closePopover();
    _popoverAnchor = anchorEl;
    const el = ensurePopover();
    positionPopover(anchorEl);
    el.innerHTML = '<div class="pql-nbedit-history-loading">Loading run history…</div>';

    // Outside-click + Esc dismissal
    _outsideClickHandler = (ev) => {
        if (!_popoverEl) return;
        if (_popoverEl.contains(ev.target)) return;
        if (_popoverAnchor && _popoverAnchor.contains(ev.target)) return;
        closePopover();
    };
    document.addEventListener('mousedown', _outsideClickHandler, true);
    _escHandler = (ev) => {
        if (ev.key === 'Escape') closePopover();
    };
    document.addEventListener('keydown', _escHandler, true);

    const ctrl = new AbortController();
    _inflightAbort = ctrl;
    try {
        const url = `/api/notebook/cell-runs?path=${encodeURIComponent(path)}`
            + `&content_hash=${encodeURIComponent(contentHash)}&limit=20`;
        const resp = await fetch(url, { signal: ctrl.signal, credentials: 'same-origin' });
        if (!resp.ok) {
            el.innerHTML = '';
            const err = document.createElement('div');
            err.className = 'pql-nbedit-history-error';
            err.textContent = `Could not load history (${resp.status}).`;
            el.appendChild(err);
            return;
        }
        const json = await resp.json();
        const runs = (json && Array.isArray(json.runs)) ? json.runs : [];
        _historyCache.set(contentHash, runs);
        el.innerHTML = '';
        const header = document.createElement('div');
        header.className = 'pql-nbedit-history-header';
        header.textContent = `Last ${runs.length} run${runs.length === 1 ? '' : 's'}`;
        el.appendChild(header);
        if (runs.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'pql-nbedit-history-empty';
            empty.textContent = 'No run history yet — execute the cell to record one.';
            el.appendChild(empty);
            return;
        }
        for (const run of runs) {
            el.appendChild(renderRunRow(run, currentSource, onRerun));
        }
    } catch (e) {
        if (ctrl.signal.aborted) return;
        el.innerHTML = '';
        const err = document.createElement('div');
        err.className = 'pql-nbedit-history-error';
        err.textContent = `Could not load history: ${e.message || e}`;
        el.appendChild(err);
    } finally {
        if (_inflightAbort === ctrl) _inflightAbort = null;
    }
}

// Convenience: cache lookup for tests / future warm-start UX.
export function cachedHistory(contentHash) {
    return _historyCache.get(contentHash) || null;
}
