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

import { sql } from '@codemirror/lang-sql';
import { bracketMatching, defaultHighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { oneDark } from '@codemirror/theme-one-dark';
import { EditorView, lineNumbers } from '@codemirror/view';

function mount(host) {
  if (host.dataset.pqlMounted === '1') return;
  host.dataset.pqlMounted = '1';
  let doc = '';
  try {
    doc = JSON.parse(host.dataset.sql || '""');
  } catch {
    doc = host.dataset.sql || '';
  }
  const isDark = document.documentElement.dataset.bsTheme === 'dark';
  new EditorView({
    state: EditorState.create({
      doc,
      extensions: [
        EditorState.readOnly.of(true),
        EditorView.editable.of(false),
        lineNumbers(),
        bracketMatching(),
        // ``defaultHighlightStyle`` is the light-theme palette;
        // ``oneDark`` ships its own highlight style.  Apply only one
        // so dark-mode keywords don't render in light-theme dark
        // colors against the dark editor background (invisible).
        ...(isDark ? [oneDark] : [syntaxHighlighting(defaultHighlightStyle)]),
        sql(),
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
