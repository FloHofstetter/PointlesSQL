/**
 * Tiny CodeMirror mount used by the visual data-product canvas editor.
 *
 * Two callable surfaces:
 *
 * * ``mountPredicateEditor(host, opts)`` — single-line shape for the
 *   Filter / CalcColumn predicate.  No line numbers, no gutters, no
 *   newline-friendly keymap; ``Enter`` is swallowed so the form stays
 *   compact.
 * * ``mountSqlEditor(host, opts)`` — full multi-line shape for the raw
 *   SQL block.  Line numbers + bracket matching + history.
 *
 * Both share the same SQL language extension + custom column
 * autocomplete: the caller supplies ``getColumns(): string[]`` and the
 * helper rebuilds the completion source on every mount (the function
 * is invoked lazily inside the source, so config drift between mount
 * and edit is fine).
 *
 * Module-level cache reuses the import-map ``@codemirror/*`` modules
 * the notebook editor already lazy-imports, so the first canvas mount
 * pays at most one network round-trip if the user has not yet visited
 * a notebook in this session.
 */

import { buildSqlSnippetCompletions } from './_codemirror_snippets.js';
import { formatSql } from './_sql_format.js';

let _cmCache = null;

async function _loadCm() {
  if (_cmCache) return _cmCache;
  const [stateMod, viewMod, commandsMod, languageMod, sqlMod, themeMod, acMod] = await Promise.all([
    import('@codemirror/state'),
    import('@codemirror/view'),
    import('@codemirror/commands'),
    import('@codemirror/language'),
    import('@codemirror/lang-sql'),
    import('@codemirror/theme-one-dark'),
    import('@codemirror/autocomplete'),
  ]);
  _cmCache = {
    EditorState: stateMod.EditorState,
    EditorView: viewMod.EditorView,
    keymap: viewMod.keymap,
    lineNumbers: viewMod.lineNumbers,
    defaultKeymap: commandsMod.defaultKeymap,
    history: commandsMod.history,
    historyKeymap: commandsMod.historyKeymap,
    syntaxHighlighting: languageMod.syntaxHighlighting,
    defaultHighlightStyle: languageMod.defaultHighlightStyle,
    bracketMatching: languageMod.bracketMatching,
    sql: sqlMod.sql,
    oneDark: themeMod.oneDark,
    autocompletion: acMod.autocompletion,
    completionKeymap: acMod.completionKeymap,
  };
  return _cmCache;
}

function _columnsCompletionSource(getColumns, includeSnippets) {
  return (context) => {
    const word = context.matchBefore(/[\w]*/);
    if (!word) return null;
    if (word.from === word.to && !context.explicit) return null;
    const columns = (typeof getColumns === 'function' ? getColumns() : []) || [];
    const options = columns.map((name) => ({
      label: name,
      type: 'variable',
      detail: 'column',
    }));
    if (includeSnippets) {
      options.push(...buildSqlSnippetCompletions());
    }
    if (!options.length) return null;
    return { from: word.from, options };
  };
}

async function _mount(host, { multiLine, initialValue, onChange, getColumns, formatOnBlur }) {
  if (!host) return null;
  if (host.dataset.pqlCanvasCmInit === '1') return null;
  host.dataset.pqlCanvasCmInit = '1';

  const cm = await _loadCm();
  const isDark = document.documentElement.dataset.bsTheme === 'dark';

  const extensions = [
    cm.sql(),
    cm.bracketMatching(),
    cm.autocompletion({
      override: [_columnsCompletionSource(getColumns, Boolean(multiLine))],
    }),
    cm.syntaxHighlighting(cm.defaultHighlightStyle),
    cm.EditorView.updateListener.of((update) => {
      if (update.docChanged && typeof onChange === 'function') {
        onChange(update.state.doc.toString());
      }
    }),
  ];

  if (multiLine) {
    extensions.unshift(cm.lineNumbers());
    extensions.push(cm.history());
    extensions.push(
      cm.keymap.of([...cm.defaultKeymap, ...cm.historyKeymap, ...cm.completionKeymap])
    );
    if (formatOnBlur !== false) {
      extensions.push(
        cm.EditorView.domEventHandlers({
          blur: (_event, view) => {
            const before = view.state.doc.toString();
            const after = formatSql(before);
            if (after && after !== before) {
              view.dispatch({
                changes: { from: 0, to: before.length, insert: after },
              });
            }
            return false;
          },
        })
      );
    }
  } else {
    // Single-line: swallow Enter so the predicate stays one row.
    extensions.push(
      cm.keymap.of([
        ...cm.defaultKeymap.filter((b) => b.key !== 'Enter'),
        ...cm.completionKeymap,
        { key: 'Enter', run: () => true },
      ])
    );
    extensions.push(
      cm.EditorState.transactionFilter.of((tr) => {
        if (!tr.changes || !tr.docChanged) return tr;
        let rejected = false;
        tr.changes.iterChanges((_fromA, _toA, _fromB, _toB, inserted) => {
          if (inserted && inserted.lines > 1) rejected = true;
        });
        return rejected ? [] : tr;
      })
    );
  }

  if (isDark) extensions.push(cm.oneDark);

  const view = new cm.EditorView({
    state: cm.EditorState.create({
      doc: initialValue || '',
      extensions,
    }),
    parent: host,
  });
  if (!multiLine) {
    host.classList.add('pql-canvas-cm-single');
  } else {
    host.classList.add('pql-canvas-cm-multi');
  }
  return {
    getValue: () => view.state.doc.toString(),
    setValue: (next) => {
      const current = view.state.doc.toString();
      if (current === next) return;
      view.dispatch({
        changes: { from: 0, to: current.length, insert: next || '' },
      });
    },
    destroy: () => {
      view.destroy();
      host.dataset.pqlCanvasCmInit = '';
      host.classList.remove('pql-canvas-cm-single', 'pql-canvas-cm-multi');
    },
  };
}

export function mountPredicateEditor(host, opts) {
  return _mount(host, { ...(opts || {}), multiLine: false });
}

export function mountSqlEditor(host, opts) {
  return _mount(host, { ...(opts || {}), multiLine: true });
}
