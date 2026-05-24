/*
 * comments_collapse.js
 *
 * Auto-collapses comment replies at depth ≥ 3 inside the
 * Discussion tab.  Each comment row carries
 * ``data-pql-comment-depth="<n>"`` (1 = top-level, 2 = first
 * reply, ...).  The script hides any descendant at depth ≥ 3
 * and inserts a "Show N more replies" toggle under the
 * deepest still-visible ancestor (depth 2).  Click expands all
 * descendants under that subtree.
 *
 * The server-side threading-depth lift went 2 → 5;
 * the current Alpine template only recurses one level so the
 * script is forward-compatible — it becomes active when the
 * recursive renderer lands and is a no-op until then.
 *
 * No framework deps.  Watches the Discussion tab subtree via
 * MutationObserver so it re-applies after Alpine re-renders.
 */

(function () {
    "use strict";

    const COLLAPSE_THRESHOLD = 3;
    const PROCESSED_FLAG = "pqlCollapseProcessed";

    function depthOf(el) {
        const raw = el.getAttribute("data-pql-comment-depth");
        if (raw === null) return null;
        const n = parseInt(raw, 10);
        return Number.isFinite(n) ? n : null;
    }

    function findAncestorAtDepth(el, target) {
        let cur = el.parentElement;
        while (cur) {
            const d = depthOf(cur);
            if (d !== null && d === target) return cur;
            cur = cur.parentElement;
        }
        return null;
    }

    function applyCollapseTo(container) {
        const rows = container.querySelectorAll(
            "[data-pql-comment-depth]"
        );
        // Map of depth-2 parent → [hidden descendants...].
        const groups = new Map();
        rows.forEach((row) => {
            if (row.dataset[PROCESSED_FLAG] === "1") return;
            const d = depthOf(row);
            if (d === null || d < COLLAPSE_THRESHOLD) return;
            const anchor = findAncestorAtDepth(row, COLLAPSE_THRESHOLD - 1);
            if (!anchor) return;
            if (!groups.has(anchor)) groups.set(anchor, []);
            groups.get(anchor).push(row);
            row.style.display = "none";
            row.dataset[PROCESSED_FLAG] = "1";
        });

        groups.forEach((hidden, anchor) => {
            if (anchor.dataset.pqlCollapseToggleAdded === "1") return;
            anchor.dataset.pqlCollapseToggleAdded = "1";
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-link btn-sm p-0 pql-comments-show-more";
            btn.textContent = `Show ${hidden.length} more repl${hidden.length === 1 ? "y" : "ies"}`;
            btn.addEventListener("click", () => {
                hidden.forEach((row) => {
                    row.style.display = "";
                });
                btn.remove();
                anchor.dataset.pqlCollapseToggleAdded = "0";
            });
            anchor.appendChild(btn);
        });
    }

    function scan(root) {
        const targets = (root || document).querySelectorAll(
            "#tab-discussion, .pql-comments-thread"
        );
        targets.forEach(applyCollapseTo);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => scan());
    } else {
        scan();
    }

    const observer = new MutationObserver(() => scan());
    const discussion = document.getElementById("tab-discussion");
    if (discussion) {
        observer.observe(discussion, { childList: true, subtree: true });
    } else {
        observer.observe(document.body, { childList: true, subtree: true });
    }
})();
