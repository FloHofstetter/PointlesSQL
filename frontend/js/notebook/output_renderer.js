// Phase 12.7 Sprint 65 — kernel-output rich-mime renderer.
//
// Render a Jupyter mime bundle by picking the richest representation
// the client can display.  Priority: html > svg > png > jpeg > json
// > plain.  Matches what nbconvert does for the "lab" template, which
// is what Sprint-26's papermill view uses.

import { ansiToHtml } from './ansi.js';

// Sprint 62: plotly / altair / bokeh emit ``<script>`` tags in their
// ``text/html`` rendering.  ``innerHTML`` does not run scripts
// (browser sandbox); we walk the subtree and re-create each
// ``<script>`` node so the parser treats the new one as executable.
// Same trick Jupyter's own renderer uses.
export function executeInlineScripts(root) {
    const scripts = root.querySelectorAll('script');
    scripts.forEach((orig) => {
        const clone = document.createElement('script');
        for (const attr of orig.attributes) {
            clone.setAttribute(attr.name, attr.value);
        }
        if (!orig.src) clone.textContent = orig.textContent || '';
        orig.replaceWith(clone);
    });
}

export function renderMimeBundle(dom, data, /* metadata */ _m) {
    if (!data || typeof data !== 'object') return;
    // Sprint 72: ipywidgets minimal placeholder.  The widget-view
    // bundle MUST win over text/html / text/plain because every
    // ipywidgets display also includes a ``text/plain`` fallback like
    // ``IntSlider(value=0)`` that we do NOT want to render — that
    // would mask the placeholder card behind a confusing repr.  Full
    // bidirectional widget rendering (vendored widget-manager,
    // round-trip ``comm_msg``) lands in a future sprint; this branch
    // keeps the cell from emitting noise + advertises the upgrade
    // path right inside the output zone.
    if (data['application/vnd.jupyter.widget-view+json']) {
        const spec = data['application/vnd.jupyter.widget-view+json'] || {};
        const card = document.createElement('div');
        card.className = 'pql-nbedit-output-widget-placeholder';
        const modelId = typeof spec.model_id === 'string' ? spec.model_id : '';
        if (modelId) {
            const idEl = document.createElement('code');
            idEl.className = 'pql-nbedit-widget-model-id';
            idEl.textContent = `model_id: ${modelId.slice(0, 8)}…`;
            card.appendChild(idEl);
            const note = document.createElement('p');
            note.className = 'pql-nbedit-widget-note';
            note.textContent = 'Interactive widgets will render in a future release. '
                + 'Install widgets in the kernel to see live updates here.';
            card.appendChild(note);
        } else {
            card.textContent = 'Widget output (unrenderable)';
        }
        dom.appendChild(card);
        return;
    }
    if (data['text/html']) {
        const wrap = document.createElement('div');
        wrap.className = 'pql-nbedit-output-html';
        // The kernel is already trusted (it runs arbitrary user code
        // as the editor user) — emitting raw HTML does not widen the
        // attack surface.  Any future sandboxing would need a
        // kernel-level sandbox, not a client-side sanitiser.
        wrap.innerHTML = Array.isArray(data['text/html'])
            ? data['text/html'].join('')
            : data['text/html'];
        dom.appendChild(wrap);
        executeInlineScripts(wrap);
        return;
    }
    if (data['image/svg+xml']) {
        const wrap = document.createElement('div');
        wrap.className = 'pql-nbedit-output-svg';
        const svg = Array.isArray(data['image/svg+xml'])
            ? data['image/svg+xml'].join('')
            : data['image/svg+xml'];
        wrap.innerHTML = svg;
        dom.appendChild(wrap);
        return;
    }
    if (data['image/png']) {
        const img = document.createElement('img');
        img.className = 'pql-nbedit-output-image';
        img.src = `data:image/png;base64,${data['image/png']}`;
        img.alt = 'output image';
        dom.appendChild(img);
        return;
    }
    if (data['image/jpeg']) {
        const img = document.createElement('img');
        img.className = 'pql-nbedit-output-image';
        img.src = `data:image/jpeg;base64,${data['image/jpeg']}`;
        img.alt = 'output image';
        dom.appendChild(img);
        return;
    }
    if (data['application/json']) {
        const pre = document.createElement('pre');
        pre.className = 'pql-nbedit-output-json';
        pre.textContent = JSON.stringify(data['application/json'], null, 2);
        dom.appendChild(pre);
        return;
    }
    if (data['text/plain']) {
        const pre = document.createElement('pre');
        pre.className = 'pql-nbedit-output-result';
        pre.textContent = Array.isArray(data['text/plain'])
            ? data['text/plain'].join('')
            : data['text/plain'];
        dom.appendChild(pre);
    }
}

// Append one rendered output frame to a cell's output zone.
// Shared path for both live kernel_msg frames and the persisted
// replay that runs on mount.  msg_type and content match Jupyter's
// wire shape; everything else (cell-end-line lookup, view-zone
// layout, autoscroll) is the orchestrator's job.
export function appendOutputFrame(dom, msgType, content) {
    switch (msgType) {
        case 'stream': {
            const pre = document.createElement('pre');
            pre.className = 'pql-nbedit-output-stream'
                + (content.name === 'stderr' ? ' pql-nbedit-output-stderr' : '');
            pre.textContent = content.text || '';
            dom.appendChild(pre);
            break;
        }
        case 'execute_result':
        case 'display_data':
            renderMimeBundle(dom, content.data || {}, content.metadata || {});
            break;
        case 'error': {
            const block = document.createElement('pre');
            block.className = 'pql-nbedit-output-error';
            const rawTb = (content.traceback || []).join('\n');
            if (rawTb) {
                block.innerHTML = ansiToHtml(rawTb);
            } else {
                block.textContent = `${content.ename}: ${content.evalue}`;
            }
            dom.appendChild(block);
            break;
        }
        case 'execute_input':
        case 'execute_reply':
            // Sprint 66: ``execute_input`` + ``execute_reply`` are
            // intercepted upstream by ``renderKernelMsg`` in
            // ``main.js`` to drive the per-cell execution-count +
            // status pills, and never reach this switch under normal
            // flow.  The cases are kept as explicit no-ops so a
            // persisted replay or a stray frame does not fall into
            // ``default`` and get silently ignored in an unclear way.
            break;
        default:
            break;
    }
}
