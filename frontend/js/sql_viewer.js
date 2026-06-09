/**
 * Read-only CodeMirror viewer for static SQL blocks.
 *
 * Recycles the same modules as the SQL editor (``frontend/js/
 * sql_editor/monaco.js``) so the syntax highlighting + theme
 * tracking matches what the user types in the editor — the
 * highlight.js github theme used to leave the saved-query detail
 * page looking unhighlighted in light mode.
 *
 * Usage::
 *
 *   <div class="pql-sql-viewer" data-sql='{{ query.sql_text|tojson }}'></div>
 *
 * On DOMContentLoaded each matching element is replaced by a
 * read-only CodeMirror instance.  ``data-sql`` is JSON-encoded so
 * embedded quotes / newlines round-trip cleanly.
 */

// CodeMirror resolves through the esm.sh import map.  These imports were
// top-level once, which welded *every* page's bootstrap (this module sits
// in bootstrap.js's static import graph) to CDN availability — an offline
// or CDN-blocked host lost the whole frontend, not just SQL highlighting.
// Load lazily on first use instead, and only on pages that carry a viewer.
let _cmModsPromise = null;
function _loadCm() {
  if (!_cmModsPromise) {
    _cmModsPromise = Promise.all([
      import('@codemirror/lang-sql'),
      import('@codemirror/language'),
      import('@codemirror/state'),
      import('@codemirror/theme-one-dark'),
      import('@codemirror/view'),
    ]).then(([sqlMod, languageMod, stateMod, themeMod, viewMod]) => ({
      sql: sqlMod.sql,
      bracketMatching: languageMod.bracketMatching,
      defaultHighlightStyle: languageMod.defaultHighlightStyle,
      syntaxHighlighting: languageMod.syntaxHighlighting,
      EditorState: stateMod.EditorState,
      oneDark: themeMod.oneDark,
      EditorView: viewMod.EditorView,
      lineNumbers: viewMod.lineNumbers,
    }));
  }
  return _cmModsPromise;
}

async function mount(host) {
  if (host.dataset.pqlMounted === '1') return;
  host.dataset.pqlMounted = '1';
  let doc = '';
  try {
    doc = JSON.parse(host.dataset.sql || '""');
  } catch {
    doc = host.dataset.sql || '';
  }
  let cm;
  try {
    cm = await _loadCm();
  } catch (_e) {
    // CDN unreachable — degrade to unhighlighted but readable text.
    const pre = document.createElement('pre');
    pre.className = 'border bg-body-tertiary p-2 small mb-0';
    pre.textContent = doc;
    host.appendChild(pre);
    return;
  }
  const isDark = document.documentElement.dataset.bsTheme === 'dark';
  new cm.EditorView({
    state: cm.EditorState.create({
      doc,
      extensions: [
        cm.EditorState.readOnly.of(true),
        cm.EditorView.editable.of(false),
        cm.lineNumbers(),
        cm.bracketMatching(),
        // ``defaultHighlightStyle`` is the light-theme palette;
        // ``oneDark`` ships its own highlight style.  Apply only one
        // so dark-mode keywords don't render in light-theme dark
        // colors against the dark editor background (invisible).
        ...(isDark ? [cm.oneDark] : [cm.syntaxHighlighting(cm.defaultHighlightStyle)]),
        cm.sql(),
      ],
    }),
    parent: host,
  });
}

function mountAll(root) {
  if (!root || !root.querySelectorAll) return;
  root.querySelectorAll('.pql-sql-viewer').forEach(mount);
}

document.addEventListener('DOMContentLoaded', () => mountAll(document));
document.addEventListener('htmx:afterSwap', (ev) => mountAll(ev.target));
