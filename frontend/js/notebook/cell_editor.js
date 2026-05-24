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
 *    by the run-history popover preview ).
 * 3. ``getSource()`` — current document text.
 * 4. ``destroy()`` — remove the EditorView and detach listeners.
 *
 * Options the parent factory passes:
 *
 * * ``initialSource`` — the cell's text on mount.
 * * ``language`` — ``'python'`` | ``'sql'`` | ``'markdown'``.
 * * ``onSourceChange(value)`` — fired on every transaction that
 *   updates the doc.  Parent uses this to flip the per-cell
 *   ``_dirty`` flag.
 * * ``yBinding`` — optional
 *   ``{ ytext, awareness, undoManager }`` triple.  When supplied,
 *   the editor swaps its local CodeMirror ``history()`` extension
 *   for ``y-codemirror.next``'s ``yCollab`` extension, which mirrors
 *   every CodeMirror transaction onto the shared ``ytext`` (then
 *   onto the WebSocket via the Phase-105.2 hub) and applies remote
 *   updates back into the editor with a remote-origin marker so the
 *   parent's dirty flag does not flip on incoming peer edits.  The
 *   ``onSourceChange`` callback still fires — driven by a
 *   ``ytext.observe`` listener — so the Alpine ``cell.source``
 *   mirror keeps up with both local and remote edits.
 */

let _cmModulesCache = null;
let _yCmModuleCache = null;

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

async function _loadYCodeMirrorModule() {
 // Pulled in lazily so unauthenticated / read-only renders don't
 // pay the y-codemirror.next download cost when no coedit client
 // ever materialises.
 if (_yCmModuleCache) return _yCmModuleCache;
 const mod = await import('y-codemirror.next');
 _yCmModuleCache = { yCollab: mod.yCollab };
 return _yCmModuleCache;
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
 yBinding = null,
} = {}) {
 return {
 _cmView: null,
 _onSourceChange: onSourceChange,
 _language: language,
 _initialSource: initialSource,
 _yBinding: yBinding,
 _ytextObserver: null,

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
 const yBindingActive = !!(
 this._yBinding && this._yBinding.ytext
 );

 // when a Y.Text is supplied, drive ``onSourceChange``
 // from the doc itself so both local + remote edits flow through the
 // same callback.  The CodeMirror update listener stays installed
 // for non-bound cells (single-tab / unauthenticated renders).
 const updateListener = EditorView.updateListener.of((update) => {
 if (!yBindingActive && update.docChanged && this._onSourceChange) {
 this._onSourceChange(update.state.doc.toString());
 }
 });

 const extensions = [
 lineNumbers(),
 highlightActiveLine(),
 // ``history()`` is replaced by yCollab's undo-manager when the
 // editor is Y-bound — running both produces double-undo on every
 // Cmd-Z.
 ...(yBindingActive ? [] : [history()]),
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
 ];

 if (yBindingActive) {
 const { yCollab } = await _loadYCodeMirrorModule();
 const { ytext, awareness, undoManager } = this._yBinding;
 extensions.push(
 yCollab(ytext, awareness || null, {
 undoManager: undoManager || undefined,
 }),
 );
 // Mirror Y.Text mutations onto the Alpine ``cell.source`` field
 // so save still serialises canonical text.  Observer fires for
 // BOTH local and remote ytext changes — local edits keep the
 // dirty flag because the parent factory's ``_onCellSourceChange``
 // sets ``_dirty = true``.  Remote-driven ytext edits also flow
 // through the same callback; the mixin's remap path (105.5)
 // takes care of cleaning up dirty flags after save.
 this._ytextObserver = () => {
 try { this._onSourceChange(ytext.toString()); }
 catch (_e) { /* swallow */ }
 };
 try { ytext.observe(this._ytextObserver); }
 catch (_e) { this._ytextObserver = null; }
 }

 // seed the CodeMirror doc from the current
 // ytext when Y-bound.  ``y-codemirror.next``'s ``yCollab`` only
 // applies *future* remote ytext mutations; it does not back-fill
 // the editor from an already-populated ytext at mount time.
 // Without this seed, a client connecting to a notebook whose
 // server-side Y.Doc already carries cell content (i.e. any tab
 // opened after the first save) sees an empty editor even though
 // ``ytext`` holds the canonical source.
 this._cmView = new EditorView({
 state: EditorState.create({
 doc: yBindingActive
 ? this._yBinding.ytext.toString()
 : this._initialSource,
 extensions,
 }),
 parent: host,
 });

 // When Y-bound and the ytext is empty but we have a non-empty
 // initialSource (brand-new cell minted in this tab), seed the
 // ytext so peers see the content.  yCollab is already wired so
 // the insert propagates through the WS.
 if (yBindingActive) {
 const { ytext } = this._yBinding;
 if (ytext.length === 0 && this._initialSource) {
 try { ytext.insert(0, this._initialSource); }
 catch (_e) { /* swallow */ }
 }
 }
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
 if (this._ytextObserver && this._yBinding && this._yBinding.ytext) {
 try { this._yBinding.ytext.unobserve(this._ytextObserver); }
 catch (_e) { /* swallow */ }
 this._ytextObserver = null;
 }
 if (this._cmView) {
 this._cmView.destroy();
 this._cmView = null;
 }
 },
 };
}
