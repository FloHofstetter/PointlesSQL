// PointlesSQL toast API.
//
// Usage (templates / other modules):
//   window.pqlToast.success("Saved.");
//   window.pqlToast.error("Upload failed: " + err.message);
//   window.pqlToast.info("Scheduler paused.", { timeout: 6000 });
//
// bootstrap.js re-attaches the singleton to ``window.pqlToast``.
// Variants map onto .pql-toast--{variant} (see style.css).  Bootstrap's
// toast JS handles show/hide; we append once, fire show, and remove
// the node on hidden.bs.toast so the DOM doesn't accumulate.
const ROOT_ID = 'pql-toast-root';
const DEFAULT_TIMEOUT = 4000;
// Phase 81.G.D — cap concurrent visible toasts so a bulk op that
// fires N requests doesn't flood the screen with N stacked cards.
// Oldest toast is dismissed in-place so the new one can show.
const MAX_VISIBLE = 3;

const VARIANTS = {
    success: { cls: 'pql-toast--success', icon: 'bi-check-circle-fill' },
    error:   { cls: 'pql-toast--error',   icon: 'bi-exclamation-octagon-fill' },
    info:    { cls: 'pql-toast--info',    icon: 'bi-info-circle-fill' },
};

function root() {
    return document.getElementById(ROOT_ID);
}

function show(variant, message, opts) {
    const host = root();
    if (!host || !window.bootstrap || !window.bootstrap.Toast) return;
    const spec = VARIANTS[variant] || VARIANTS.info;
    const timeout = (opts && typeof opts.timeout === 'number') ? opts.timeout : DEFAULT_TIMEOUT;

    // Evict the oldest toast(s) FIFO so MAX_VISIBLE is the upper bound
    // after this one is appended.  We count every .toast still in the
    // DOM (not just .show) because rapid-fire callers may stack faster
    // than Bootstrap's animation can apply .show.  hidden.bs.toast
    // removes the node, so live count == queued + visible.
    const existing = host.querySelectorAll('.toast');
    if (existing.length >= MAX_VISIBLE) {
        const toEvict = existing.length - MAX_VISIBLE + 1;
        for (let i = 0; i < toEvict; i++) {
            const inst = window.bootstrap.Toast.getOrCreateInstance(existing[i]);
            inst.hide();
        }
    }

    const node = document.createElement('div');
    node.className = 'toast pql-toast ' + spec.cls;
    node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
    node.setAttribute('aria-atomic', 'true');

    const body = document.createElement('div');
    body.className = 'pql-toast__body';

    const icon = document.createElement('i');
    icon.className = 'bi ' + spec.icon + ' pql-toast__icon';
    icon.setAttribute('aria-hidden', 'true');

    const text = document.createElement('span');
    text.className = 'pql-toast__message';
    text.textContent = String(message == null ? '' : message);

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn-close btn-close-white ms-2';
    close.setAttribute('data-bs-dismiss', 'toast');
    close.setAttribute('aria-label', 'Close');

    body.appendChild(icon);
    body.appendChild(text);
    body.appendChild(close);
    node.appendChild(body);
    host.appendChild(node);

    const toast = new window.bootstrap.Toast(node, { delay: timeout });
    node.addEventListener('hidden.bs.toast', function () {
        node.remove();
    });
    toast.show();
}

export const pqlToast = {
    success: function (msg, opts) { show('success', msg, opts); },
    error:   function (msg, opts) { show('error',   msg, opts); },
    info:    function (msg, opts) { show('info',    msg, opts); },
};
