/*
 * mention_autocomplete.js — Phase 76.6.1
 *
 * Token-aware typeahead for the Discussion comment textarea.
 * Watches keystrokes for one of four prefixes and renders a
 * dropdown of matches the user can pick.  No framework deps —
 * raw DOM + fetch + debounce.
 *
 *   @<frag>        → /api/users/search?q=<frag>      → "@<email>"
 *   #dp:<frag>     → /api/data-products?q=<frag>     → "#dp:<cat>.<sch>"
 *   #topic:<frag>  → /api/topics?q=<frag>            → "#topic:<slug>"
 *   #agent:<frag>  → /api/agents?q=<frag>            → "#agent:<slug>"
 *
 * Wire-in: drop ``data-mention-autocomplete`` on any textarea
 * you want enriched and load this script anywhere on the page.
 */

(function () {
    "use strict";

    const DEBOUNCE_MS = 200;
    const MIN_QUERY = 1;

    const TRIGGERS = [
        {
            prefix: "@",
            url: (q) => `/api/users/search?q=${encodeURIComponent(q)}`,
            parse: (data) => (data.results || data.users || []).slice(0, 8),
            label: (row) => row.display_name || row.email,
            insert: (row) => `@${row.email}`,
        },
        {
            prefix: "#dp:",
            url: (q) => `/api/data-products?q=${encodeURIComponent(q)}`,
            parse: (data) => (data.data_products || data.items || data || []).slice(0, 8),
            label: (row) => `${row.catalog || row.catalog_name}.${row.schema || row.schema_name}`,
            insert: (row) => `#dp:${row.catalog || row.catalog_name}.${row.schema || row.schema_name}`,
        },
        {
            prefix: "#topic:",
            url: (q) => `/api/topics?q=${encodeURIComponent(q)}`,
            parse: (data) => (data.topics || data.items || data || []).slice(0, 8),
            label: (row) => row.display_name || row.slug,
            insert: (row) => `#topic:${row.slug}`,
        },
        {
            prefix: "#agent:",
            url: (q) => `/api/agents?q=${encodeURIComponent(q)}`,
            parse: (data) => (data.agents || data.items || data || []).slice(0, 8),
            label: (row) => row.display_name || row.slug,
            insert: (row) => `#agent:${row.slug}`,
        },
    ];

    function findTrigger(text, caret) {
        // Walk backwards from caret to find one of the trigger prefixes.
        // Stop at whitespace, comma, or BOM — those bound the token.
        const slice = text.slice(0, caret);
        for (const trig of TRIGGERS) {
            const idx = slice.lastIndexOf(trig.prefix);
            if (idx === -1) continue;
            const between = slice.slice(idx + trig.prefix.length);
            // Token must not contain whitespace or newline.
            if (/[\s]/.test(between)) continue;
            // Guard against '#dp:' matching inside '#topic:foo' etc.
            if (trig.prefix === "@") {
                // '@' should not be preceded by an alphanumeric
                // (so we don't trigger on "alice@example.com").
                if (idx > 0 && /\w/.test(slice[idx - 1])) continue;
            }
            return { trig, start: idx, query: between };
        }
        return null;
    }

    function debounce(fn, ms) {
        let timer = null;
        return (...args) => {
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => fn(...args), ms);
        };
    }

    function makePicker() {
        const ul = document.createElement("ul");
        ul.className = "pql-mention-picker list-group position-absolute shadow-sm";
        ul.style.zIndex = "1050";
        ul.style.display = "none";
        ul.style.maxHeight = "240px";
        ul.style.overflowY = "auto";
        ul.style.minWidth = "240px";
        document.body.appendChild(ul);
        return ul;
    }

    function positionPicker(picker, textarea) {
        const rect = textarea.getBoundingClientRect();
        picker.style.left = (window.scrollX + rect.left) + "px";
        picker.style.top = (window.scrollY + rect.bottom + 2) + "px";
    }

    function attach(textarea) {
        if (textarea.dataset.mentionAutocompleteWired === "1") return;
        textarea.dataset.mentionAutocompleteWired = "1";

        const picker = makePicker();
        let active = null;       // { trig, start, query }
        let entries = [];
        let highlight = 0;
        let aborter = null;

        const hide = () => {
            picker.style.display = "none";
            entries = [];
            highlight = 0;
            active = null;
        };

        const render = () => {
            picker.innerHTML = "";
            if (entries.length === 0) {
                hide();
                return;
            }
            entries.forEach((row, i) => {
                const li = document.createElement("li");
                li.className = "list-group-item list-group-item-action py-1 px-2 small";
                if (i === highlight) li.classList.add("active");
                li.textContent = active.trig.label(row);
                li.addEventListener("mousedown", (ev) => {
                    ev.preventDefault();
                    select(i);
                });
                picker.appendChild(li);
            });
            positionPicker(picker, textarea);
            picker.style.display = "block";
        };

        const select = (idx) => {
            if (!active || !entries[idx]) return;
            const row = entries[idx];
            const inserted = active.trig.insert(row) + " ";
            const before = textarea.value.slice(0, active.start);
            const after = textarea.value.slice(textarea.selectionStart);
            textarea.value = before + inserted + after;
            const caret = before.length + inserted.length;
            textarea.setSelectionRange(caret, caret);
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
            hide();
            textarea.focus();
        };

        const fetchMatches = debounce(async (state) => {
            if (!state || state.query.length < MIN_QUERY) {
                entries = [];
                render();
                return;
            }
            if (aborter) aborter.abort();
            aborter = new AbortController();
            try {
                const res = await fetch(state.trig.url(state.query), {
                    signal: aborter.signal,
                    credentials: "same-origin",
                });
                if (!res.ok) {
                    entries = [];
                    render();
                    return;
                }
                const data = await res.json();
                entries = state.trig.parse(data);
                highlight = 0;
                render();
            } catch (err) {
                if (err && err.name === "AbortError") return;
                entries = [];
                render();
            }
        }, DEBOUNCE_MS);

        textarea.addEventListener("input", () => {
            const next = findTrigger(textarea.value, textarea.selectionStart);
            if (!next) {
                hide();
                return;
            }
            active = next;
            fetchMatches(next);
        });

        textarea.addEventListener("keydown", (ev) => {
            if (picker.style.display !== "block" || entries.length === 0) return;
            if (ev.key === "ArrowDown") {
                ev.preventDefault();
                highlight = (highlight + 1) % entries.length;
                render();
            } else if (ev.key === "ArrowUp") {
                ev.preventDefault();
                highlight = (highlight - 1 + entries.length) % entries.length;
                render();
            } else if (ev.key === "Enter" || ev.key === "Tab") {
                ev.preventDefault();
                select(highlight);
            } else if (ev.key === "Escape") {
                hide();
            }
        });

        textarea.addEventListener("blur", () => {
            // Defer so click events on the picker land first.
            setTimeout(hide, 120);
        });
    }

    function scanAndAttach(root) {
        const targets = (root || document).querySelectorAll(
            "textarea[data-mention-autocomplete]"
        );
        targets.forEach(attach);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => scanAndAttach());
    } else {
        scanAndAttach();
    }

    // Re-scan whenever Alpine swaps the discussion tab in.
    const observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
            m.addedNodes.forEach((n) => {
                if (n.nodeType === 1) scanAndAttach(n);
            });
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
