/*
 * PointlesSQL toast API — Sprint 30.
 *
 * Usage:
 *   window.pqlToast.success("Saved.");
 *   window.pqlToast.error("Upload failed: " + err.message);
 *   window.pqlToast.info("Scheduler paused.", { timeout: 6000 });
 *
 * Variants map onto .pql-toast--{variant} (see style.css). Bootstrap's
 * toast JS handles show/hide; we append once, fire show, and remove
 * the node on hidden.bs.toast so the DOM doesn't accumulate.
 */
(function () {
    var ROOT_ID = "pql-toast-root";
    var DEFAULT_TIMEOUT = 4000;

    var VARIANTS = {
        success: { cls: "pql-toast--success", icon: "bi-check-circle-fill" },
        error:   { cls: "pql-toast--error",   icon: "bi-exclamation-octagon-fill" },
        info:    { cls: "pql-toast--info",    icon: "bi-info-circle-fill" },
    };

    function root() {
        return document.getElementById(ROOT_ID);
    }

    function show(variant, message, opts) {
        var host = root();
        if (!host || !window.bootstrap || !window.bootstrap.Toast) return;
        var spec = VARIANTS[variant] || VARIANTS.info;
        var timeout = (opts && typeof opts.timeout === "number") ? opts.timeout : DEFAULT_TIMEOUT;

        var node = document.createElement("div");
        node.className = "toast pql-toast " + spec.cls;
        node.setAttribute("role", "status");
        node.setAttribute("aria-live", "polite");
        node.setAttribute("aria-atomic", "true");

        var body = document.createElement("div");
        body.className = "pql-toast__body";

        var icon = document.createElement("i");
        icon.className = "bi " + spec.icon + " pql-toast__icon";
        icon.setAttribute("aria-hidden", "true");

        var text = document.createElement("span");
        text.className = "pql-toast__message";
        text.textContent = String(message == null ? "" : message);

        var close = document.createElement("button");
        close.type = "button";
        close.className = "btn-close btn-close-white ms-2";
        close.setAttribute("data-bs-dismiss", "toast");
        close.setAttribute("aria-label", "Close");

        body.appendChild(icon);
        body.appendChild(text);
        body.appendChild(close);
        node.appendChild(body);
        host.appendChild(node);

        var toast = new window.bootstrap.Toast(node, { delay: timeout });
        node.addEventListener("hidden.bs.toast", function () {
            node.remove();
        });
        toast.show();
    }

    window.pqlToast = {
        success: function (msg, opts) { show("success", msg, opts); },
        error:   function (msg, opts) { show("error",   msg, opts); },
        info:    function (msg, opts) { show("info",    msg, opts); },
    };
})();
