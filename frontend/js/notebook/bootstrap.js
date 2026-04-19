// Phase 12.7 Sprint 65 — ESM entry that exposes the notebook-editor
// Alpine factory as `window.notebookEditor`.
//
// Alpine resolves x-data="notebookEditor({...})" via the global
// scope; its expression evaluator does not import ESM modules.  The
// module split therefore lives behind this thin bootstrap that
// imports the orchestrator and assigns it once.  All other modules
// stay tree-shakable / individually testable.

import { createNotebookEditor } from './main.js';

window.notebookEditor = createNotebookEditor;
