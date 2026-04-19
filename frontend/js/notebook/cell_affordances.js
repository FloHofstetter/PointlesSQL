// Phase 12.7 Sprint 66 — per-cell affordances (run button, status
// pill, execution-count pill, elapsed-time pill, ``+`` inserter).
//
// Two Monaco view zones per cell:
//
// 1. Toolbar zone — 26px tall, anchored above the cell's marker line
//    (``afterLineNumber = markerLine - 1``).  Holds the run button +
//    status / count / elapsed pills.
// 2. Inserter zone — 22px tall, anchored after the cell's last body
//    line.  Hover-revealed ``+ Code`` / ``+ Markdown`` buttons.
//
// View zones were chosen over Monaco content widgets because they
// reserve vertical space (no overlap with markdown preview zones)
// and they mirror the outputZones / markdownZones shape already used
// in ``main.js``.  Each cell's toolbar and inserter live in one
// closure-scoped record so ``removeAffordances`` can dispose both in
// a single editor mutation.
//
// Closure-state invariant (Sprint 65 / BUG-64-02): DOM nodes, zone
// handles, and timers tracked here never flow into Alpine's
// reactive proxy.  The record lives in a closure-scoped map inside
// the orchestrator.

import { getCellType } from './cell_types.js';

const ELAPSED_TICK_MS = 100;

function formatElapsed(ms) {
    if (!Number.isFinite(ms) || ms < 0) return '';
    if (ms < 1000) return `${ms}ms`;
    const s = ms / 1000;
    if (s < 10) return `${s.toFixed(2)}s`;
    if (s < 60) return `${s.toFixed(1)}s`;
    const mins = Math.floor(s / 60);
    const rem = Math.floor(s % 60);
    return `${mins}m${rem.toString().padStart(2, '0')}s`;
}

function makeToolbarDom(cellId, typeId, onRun, onTogglePin) {
    const root = document.createElement('div');
    root.className = 'pql-nbedit-cell-toolbar';
    root.dataset.cellId = cellId;
    root.dataset.cellType = typeId;

    const descriptor = getCellType(typeId);

    let runBtn = null;
    if (descriptor.canExecute) {
        runBtn = document.createElement('button');
        runBtn.type = 'button';
        runBtn.className = 'pql-nbedit-run-btn';
        runBtn.title = 'Run this cell (Shift+Enter)';
        runBtn.textContent = '▶';
        runBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            ev.preventDefault();
            onRun();
        });
        // Swallow mousedown so Monaco doesn't steal focus from the
        // button before the click fires.
        runBtn.addEventListener('mousedown', (ev) => ev.stopPropagation());
        root.appendChild(runBtn);
    }

    const countEl = document.createElement('span');
    countEl.className = 'pql-nbedit-exec-count';
    countEl.textContent = descriptor.canExecute ? '[ ]' : '';
    root.appendChild(countEl);

    const statusEl = document.createElement('span');
    statusEl.className = 'pql-nbedit-status-pill pql-nbedit-status-idle';
    statusEl.textContent = descriptor.canExecute ? 'idle' : descriptor.label.toLowerCase();
    root.appendChild(statusEl);

    const elapsedEl = document.createElement('span');
    elapsedEl.className = 'pql-nbedit-elapsed';
    elapsedEl.textContent = '';
    root.appendChild(elapsedEl);

    const labelEl = document.createElement('span');
    labelEl.className = 'pql-nbedit-cell-label';
    labelEl.textContent = descriptor.label;
    root.appendChild(labelEl);

    // Sprint 69: per-cell pin toggle for cell types that opt into it
    // (currently markdown only, registered via descriptor.affordances).
    // The button reflects the *requested* state — main.js owns the
    // source-of-truth flag in the closure-scoped markdownZones map and
    // calls ``setPinState`` after toggling.
    let pinBtn = null;
    if (Array.isArray(descriptor.affordances) && descriptor.affordances.includes('pin')) {
        pinBtn = document.createElement('button');
        pinBtn.type = 'button';
        pinBtn.className = 'pql-nbedit-pin-btn';
        pinBtn.title = 'Pin to source view';
        pinBtn.innerHTML = '<i class="bi bi-pencil"></i>';
        pinBtn.dataset.pinned = 'false';
        pinBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            ev.preventDefault();
            onTogglePin();
        });
        pinBtn.addEventListener('mousedown', (ev) => ev.stopPropagation());
        root.appendChild(pinBtn);
    }

    return { root, runBtn, statusEl, countEl, elapsedEl, pinBtn };
}

function makeInserterDom(cellId, onInsert) {
    const root = document.createElement('div');
    root.className = 'pql-nbedit-inserter';
    root.dataset.cellId = cellId;

    const mkBtn = (label, typeId) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pql-nbedit-inserter-btn';
        btn.textContent = label;
        btn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            ev.preventDefault();
            onInsert(typeId);
        });
        btn.addEventListener('mousedown', (ev) => ev.stopPropagation());
        return btn;
    };
    root.appendChild(mkBtn('+ Code', 'code'));
    root.appendChild(mkBtn('+ Markdown', 'markdown'));
    return root;
}

export function mountAffordances(editor, cellId, typeId, markerLine, handlers) {
    const { root, runBtn, statusEl, countEl, elapsedEl, pinBtn } = makeToolbarDom(
        cellId,
        typeId,
        () => handlers.onRun(cellId),
        () => handlers.onTogglePin && handlers.onTogglePin(cellId),
    );
    // Toolbar sits on the line immediately above the marker.
    // ``afterLineNumber: 0`` is valid and places the zone above
    // line 1 — which is what the first cell needs.
    const afterLineNumber = Math.max(0, markerLine - 1);
    let zoneId = null;
    editor.changeViewZones((accessor) => {
        zoneId = accessor.addZone({
            afterLineNumber,
            heightInPx: 26,
            domNode: root,
        });
    });

    return {
        toolbarZone: { zoneId, domNode: root, afterLineNumber },
        inserterZone: null,
        runBtn,
        pinBtn,
        rootEl: root,
        statusEl,
        countEl,
        elapsedEl,
        startedAt: null,
        elapsedIntervalId: null,
        status: 'idle',
        typeId,
    };
}

// Sprint 69: reflect the pin flag onto the pencil button.  Called by
// main.js after toggling ``markdownZones[cellId].editModePinned``.
// No-op on cells whose descriptor does not include the ``pin``
// affordance.
export function setPinState(record, pinned) {
    if (!record || !record.pinBtn) return;
    record.pinBtn.dataset.pinned = pinned ? 'true' : 'false';
    record.pinBtn.title = pinned ? 'Unpin (return to preview)' : 'Pin to source view';
    record.pinBtn.innerHTML = pinned
        ? '<i class="bi bi-pencil-fill"></i>'
        : '<i class="bi bi-pencil"></i>';
    record.pinBtn.classList.toggle('pql-nbedit-pin-btn-active', !!pinned);
}

export function mountInserter(editor, cellId, afterLineNumber, handlers) {
    const dom = makeInserterDom(cellId, (typeId) => handlers.onInsert(cellId, typeId));
    let zoneId = null;
    editor.changeViewZones((accessor) => {
        zoneId = accessor.addZone({
            afterLineNumber,
            heightInPx: 22,
            domNode: dom,
        });
    });
    return { zoneId, domNode: dom, afterLineNumber };
}

export function moveZone(editor, zone, afterLineNumber, heightInPx) {
    if (!zone) return;
    if (zone.afterLineNumber === afterLineNumber) return;
    editor.changeViewZones((accessor) => {
        accessor.removeZone(zone.zoneId);
        zone.zoneId = accessor.addZone({
            afterLineNumber,
            heightInPx,
            domNode: zone.domNode,
        });
    });
    zone.afterLineNumber = afterLineNumber;
}

export function moveToolbar(editor, record, markerLine) {
    if (!record || !record.toolbarZone) return;
    moveZone(editor, record.toolbarZone, Math.max(0, markerLine - 1), 26);
}

export function moveInserter(editor, inserter, afterLineNumber) {
    if (!inserter) return;
    moveZone(editor, inserter, afterLineNumber, 22);
}

export function removeAffordances(editor, record) {
    if (!record) return;
    stopElapsed(record);
    if (record.toolbarZone) {
        try {
            editor.changeViewZones((accessor) => {
                accessor.removeZone(record.toolbarZone.zoneId);
            });
        } catch {}
        record.toolbarZone = null;
    }
    if (record.inserterZone) {
        try {
            editor.changeViewZones((accessor) => {
                accessor.removeZone(record.inserterZone.zoneId);
            });
        } catch {}
        record.inserterZone = null;
    }
}

export function setStatus(record, status) {
    if (!record || !record.statusEl) return;
    record.status = status;
    const el = record.statusEl;
    el.className = `pql-nbedit-status-pill pql-nbedit-status-${status}`;
    const label = {
        idle: 'idle',
        running: 'running',
        ok: 'ok',
        error: 'error',
        cancelled: 'cancelled',
    }[status] || status;
    el.textContent = label;
}

export function setExecutionCount(record, n) {
    if (!record || !record.countEl) return;
    if (n === '*') {
        record.countEl.textContent = '[*]';
    } else if (n === null || n === undefined) {
        record.countEl.textContent = '[ ]';
    } else {
        record.countEl.textContent = `[${n}]`;
    }
}

export function startElapsed(record) {
    if (!record || !record.elapsedEl) return;
    stopElapsed(record);
    record.startedAt = Date.now();
    record.elapsedEl.textContent = '0ms';
    record.elapsedIntervalId = window.setInterval(() => {
        if (record.startedAt === null) return;
        record.elapsedEl.textContent = formatElapsed(Date.now() - record.startedAt);
    }, ELAPSED_TICK_MS);
}

export function stopElapsed(record) {
    if (!record) return;
    if (record.elapsedIntervalId !== null && record.elapsedIntervalId !== undefined) {
        window.clearInterval(record.elapsedIntervalId);
        record.elapsedIntervalId = null;
    }
    if (record.startedAt !== null && record.elapsedEl) {
        record.elapsedEl.textContent = formatElapsed(Date.now() - record.startedAt);
    }
    record.startedAt = null;
}

export function resetElapsed(record) {
    if (!record || !record.elapsedEl) return;
    stopElapsed(record);
    record.elapsedEl.textContent = '';
}
