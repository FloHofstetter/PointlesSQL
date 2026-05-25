/**
 * SQL editor — CodeMirror lifecycle + autocomplete source.
 *
 * Split out of ``sql_editor.js``. Owns the dynamic
 * ``import('@codemirror/...')`` graph (lazy-loaded so non-/sql pages
 * don't pay the 200 kB+ download), the per-instance ``EditorView``
 * setup, the keymap that wires Cmd-Enter → ``run()`` and Cmd-S →
 * ``openSaveModal()``, the deep-link prefill, the keyboard ``c``
 * shortcut to toggle table↔chart, and the catalog-tree-driven
 * autocomplete source.
 *
 * Closure state from the earlier single-file shape lives on
 * ``this._cmView`` + ``this._catalogCompletions`` so the other three
 * sub-modules (execute, saved, chart) can reach the EditorView
 * through ``this``.
 */

function flattenTree(tree) {
  const out = [];
  for (const cat of tree || []) {
    const catName = cat && cat.name;
    if (!catName) continue;
    for (const sch of cat.schemas || []) {
      const schName = sch && sch.name;
      if (!schName) continue;
      for (const tbl of sch.tables || []) {
        const tblName = tbl && tbl.name;
        if (!tblName) continue;
        out.push(`${catName}.${schName}.${tblName}`);
      }
    }
  }
  return out;
}

export const monacoMethods = {
  async init() {
    const host = document.getElementById('pql-sql-editor-root');
    // Synchronous re-entry guard: Alpine walks the tree twice in
    // some init paths and both calls race through the dynamic
    // imports before ``_cmView`` is set, yielding two CodeMirror
    // instances in the same host. Flag the host ourselves.
    if (!host || host.dataset.pqlCmInit === '1') return;
    host.dataset.pqlCmInit = '1';

    const [stateMod, viewMod, commandsMod, languageMod, sqlMod, themeMod, autocompleteMod] =
      await Promise.all([
        import('@codemirror/state'),
        import('@codemirror/view'),
        import('@codemirror/commands'),
        import('@codemirror/language'),
        import('@codemirror/lang-sql'),
        import('@codemirror/theme-one-dark'),
        import('@codemirror/autocomplete'),
      ]);
    const { EditorState } = stateMod;
    const { EditorView, keymap, highlightActiveLine, lineNumbers } = viewMod;
    const { defaultKeymap, history, historyKeymap } = commandsMod;
    const { syntaxHighlighting, defaultHighlightStyle, bracketMatching } = languageMod;
    const { sql } = sqlMod;
    const { oneDark } = themeMod;
    const { autocompletion, completionKeymap } = autocompleteMod;

    const runShortcut = {
      key: 'Mod-Enter',
      run: () => {
        this.run();
        return true;
      },
      preventDefault: true,
    };
    const saveShortcut = {
      key: 'Mod-s',
      run: () => {
        this.openSaveModal();
        return true;
      },
      preventDefault: true,
    };

    // Honour ?prefill=<urlencoded sql> so the /queries re-run
    // button and future deep-links open with a pre-filled query.
    // Clean the URL so a reload isn't a second re-run.
    const qs = new URLSearchParams(window.location.search);
    const prefill = qs.get('prefill');
    const startingDoc = prefill && prefill.trim() ? prefill : 'SELECT 1 AS n';
    if (prefill) {
      try {
        history.replaceState({}, '', '/sql');
      } catch (e) {
        /* ignore */
      }
    }

    const self = this;
    function tableCompletionSource(context) {
      const completions = self._catalogCompletions || [];
      if (!completions.length) return null;
      const word = context.matchBefore(/[\w.]*/);
      if (!word || (word.from === word.to && !context.explicit)) {
        return null;
      }
      return {
        from: word.from,
        options: completions.map((full) => ({
          label: full,
          type: 'class',
          boost: 1,
        })),
      };
    }

    // Apply the dark theme only when the page itself is in dark mode.
    // CodeMirror's oneDark hard-codes a dark palette, so on a light
    // page it leaves the editor as a black panel that doesn't match
    // the surrounding card.  Bootstrap mirrors the user's pick onto
    // the html element via ``data-bs-theme`` — read it here, and let
    // the editor fall back to the default light syntax-highlight.
    //
    // Apply only ONE highlight style — ``defaultHighlightStyle`` is
    // the light palette, ``oneDark`` ships its own.  Loading both
    // makes the dark-mode keywords render in the light style's dark
    // colors, invisible against the oneDark background.
    const isDark = document.documentElement.dataset.bsTheme === 'dark';
    this._cmView = new EditorView({
      state: EditorState.create({
        doc: startingDoc,
        extensions: [
          lineNumbers(),
          highlightActiveLine(),
          history(),
          bracketMatching(),
          ...(isDark ? [oneDark] : [syntaxHighlighting(defaultHighlightStyle)]),
          sql(),
          autocompletion({ override: [tableCompletionSource] }),
          keymap.of([
            runShortcut,
            saveShortcut,
            ...completionKeymap,
            ...defaultKeymap,
            ...historyKeymap,
          ]),
        ],
      }),
      parent: host,
    });
    this.refreshSaved();
    this.refreshCompletions();
    // global ``c`` toggles table ↔ chart when the
    // focus isn't inside CodeMirror or a form control.
    this._onKeydown = this._onKeydown.bind(this);
    window.addEventListener('keydown', this._onKeydown);
    // if the page was deep-linked with
    // ?history_id=<id> (from a /queries row re-run), fetch
    // the persisted chart config and seed the toolbar.
    const histId = qs.get('history_id');
    if (histId) {
      const id = parseInt(histId, 10);
      if (!Number.isNaN(id)) this.seedFromHistory(id);
    }
  },

  destroy() {
    if (this._onKeydown) {
      window.removeEventListener('keydown', this._onKeydown);
    }
    this.destroyChart();
    if (this._chartSaveTimer) {
      clearTimeout(this._chartSaveTimer);
      this._chartSaveTimer = null;
    }
  },

  _onKeydown(ev) {
    if (ev.key !== 'c' || ev.ctrlKey || ev.metaKey || ev.altKey) {
      return;
    }
    const active = document.activeElement;
    if (!active) {
      this.toggleView();
      return;
    }
    const tag = (active.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    // CodeMirror's inner contenteditable host sits inside
    // #pql-sql-editor-root; leave typing alone when focus is there.
    const host = document.getElementById('pql-sql-editor-root');
    if (host && host.contains(active)) return;
    ev.preventDefault();
    this.toggleView();
  },

  setSQL(value) {
    if (!this._cmView) return;
    this._cmView.dispatch({
      changes: { from: 0, to: this._cmView.state.doc.length, insert: value || '' },
    });
  },

  getSQL() {
    if (!this._cmView) return '';
    return this._cmView.state.doc.toString();
  },

  async refreshCompletions() {
    // /api/tree already exists for the sidebar; we reuse it as the
    // autocomplete source. Non-admin callers see only catalogs
    // they have USE on, which is the correct scope for autocomplete
    // anyway — you should not see tables you can't query.
    const res = await window.pqlApi.fetch('/api/tree', { silent: true });
    if (res.ok && Array.isArray(res.data)) {
      this._catalogCompletions = flattenTree(res.data);
    }
  },
};
