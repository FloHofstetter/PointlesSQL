/**
 * Per-cell CodeMirror editor — reusable Alpine factory.
 *
 * One ``cellEditor()`` instance per notebook cell.  Encapsulates the
 * dynamic ``import('@codemirror/...')`` graph, the per-instance
 * ``EditorView``, the language extension switch (python / sql /
 * markdown), and the dark-mode-aware theme application.  Designed so
 * the parent ``notebookEditor()`` factory can spin up dozens of cells
 * on one page without state-cross-talk — every cell carries its own
 * closure-scoped ``EditorView`` reference and never reaches into a
 * sibling.
 *
 * Lifecycle:
 *
 * 1. ``mount(host)`` — call once after the cell's DOM node exists.
 *    Loads CodeMirror modules lazily (cached at the module level so
 *    only the first cell pays the dynamic-import cost), installs the
 *    matching language extension, and wires the editor's onChange
 *    callback to ``onSourceChange``.
 * 2. ``setSource(value)`` — programmatic source replacement (used
 *    by the run-history popover preview in Sprint 66.7).
 * 3. ``getSource()`` — current document text.
 * 4. ``destroy()`` — remove the EditorView and detach listeners.
 *
 * Three options the parent factory passes:
 *
 * * ``initialSource`` — the cell's text on mount.
 * * ``language`` — ``'python'`` | ``'sql'`` | ``'markdown'``.
 * * ``onSourceChange(value)`` — fired on every transaction that
 *   updates the doc.  Parent uses this to flip the per-cell
 *   ``_dirty`` flag (Sprint 66.2).
 */

let _cmModulesCache = null;

async function _loadCodeMirrorModules() {
 if (_cmModulesCache) return _cmModulesCache;
 const [
 stateMod, viewMod, commandsMod, languageMod,
 sqlMod, pythonMod, markdownMod, themeMod,
 ] = await Promise.all([
 import('@codemirror/state'),
 import('@codemirror/view'),
 import('@codemirror/commands'),
 import('@codemirror/language'),
 import('@codemirror/lang-sql'),
 import('@codemirror/lang-python'),
 import('@codemirror/lang-markdown'),
 import('@codemirror/theme-one-dark'),
 ]);
 _cmModulesCache = {
 EditorState: stateMod.EditorState,
 EditorView: viewMod.EditorView,
 keymap: viewMod.keymap,
 highlightActiveLine: viewMod.highlightActiveLine,
 lineNumbers: viewMod.lineNumbers,
 defaultKeymap: commandsMod.defaultKeymap,
 history: commandsMod.history,
 historyKeymap: commandsMod.historyKeymap,
 syntaxHighlighting: languageMod.syntaxHighlighting,
 defaultHighlightStyle: languageMod.defaultHighlightStyle,
 bracketMatching: languageMod.bracketMatching,
 sql: sqlMod.sql,
 python: pythonMod.python,
 markdown: markdownMod.markdown,
 oneDark: themeMod.oneDark,
 };
 return _cmModulesCache;
}

function _languageExtension(modules, language) {
 if (language === 'sql') return modules.sql();
 if (language === 'markdown') return modules.markdown();
 return modules.python();
}

export function cellEditor({
 initialSource = '',
 language = 'python',
 onSourceChange = () => {},
} = {}) {
 return {
 _cmView: null,
 _onSourceChange: onSourceChange,
 _language: language,
 _initialSource: initialSource,

 async mount(host) {
 if (!host || host.dataset.pqlCellInit === '1') return;
 host.dataset.pqlCellInit = '1';
 const modules = await _loadCodeMirrorModules();
 const {
 EditorState, EditorView, keymap, highlightActiveLine, lineNumbers,
 defaultKeymap, history, historyKeymap,
 syntaxHighlighting, defaultHighlightStyle, bracketMatching,
 oneDark,
 } = modules;

 const isDark = document.documentElement.dataset.bsTheme === 'dark';
 const updateListener = EditorView.updateListener.of((update) => {
 if (update.docChanged && this._onSourceChange) {
 this._onSourceChange(update.state.doc.toString());
 }
 });

 this._cmView = new EditorView({
 state: EditorState.create({
 doc: this._initialSource,
 extensions: [
 lineNumbers(),
 highlightActiveLine(),
 history(),
 bracketMatching(),
 ...(isDark
 ? [oneDark]
 : [syntaxHighlighting(defaultHighlightStyle)]),
 _languageExtension(modules, this._language),
 keymap.of([
 ...defaultKeymap,
 ...historyKeymap,
 ]),
 updateListener,
 ],
 }),
 parent: host,
 });
 },

 setSource(value) {
 if (!this._cmView) return;
 this._cmView.dispatch({
 changes: {
 from: 0,
 to: this._cmView.state.doc.length,
 insert: value || '',
 },
 });
 },

 getSource() {
 if (!this._cmView) return this._initialSource;
 return this._cmView.state.doc.toString();
 },

 focus() {
 if (this._cmView) this._cmView.focus();
 },

 destroy() {
 if (this._cmView) {
 this._cmView.destroy();
 this._cmView = null;
 }
 },
 };
}
