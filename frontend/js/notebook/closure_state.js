// Phase 12.7 Sprint 65 — Alpine-reactivity boundary helper.
//
// createClosureRefs(names): a sealed bag of mutable refs that NEVER
// leaves the factory closure.  The returned helper itself stays a
// closure-local `const`; assigning it to `this.X` would defeat the
// purpose.
//
// Why this exists
// ---------------
// Alpine wraps every property of an x-data return value in a
// deep-reactive Vue Proxy.  Passing such a proxy into
// monaco.editor.create({model}) — or any third-party that does deep
// introspection (Web Workers, jsonschema validators, libraries with
// circular references) — can hang the synchronous call indefinitely
// as the proxy chain interacts with internal cycles.
//
// Sprint-64 BUG-64-02 (commit 0af7984) was exactly this: storing
// the Monaco model on `this._model` then handing it to
// `monaco.editor.create({model: this._model})` made Monaco stall at
// 1 % CPU with no console.error.  Standalone Monaco repro: 80 ms.
// Same code under Alpine: never returns.
//
// The fix in Sprint 64 was a plain closure-scoped `let _editor` /
// `let _model`; that worked but lived as inline mahnung in 1500
// LoC of IIFE.  Sprint 65 promotes the pattern to this helper +
// a CI grep gate (scripts/check-frontend-no-reactive-monaco.sh)
// that fails on `this._(editor|model|monaco|worker|...)` assignments
// inside frontend/js/notebook/.  Belt and suspenders.
//
// Usage
// -----
//
//   import { createClosureRefs } from './closure_state.js';
//
//   export function notebookEditor(opts) {
//       const refs = createClosureRefs(['editor', 'model']);
//       return {
//           // primitive reactive UI state only goes on the
//           // returned object — saveState, kernelStatus, etc.
//           saveState: 'saved',
//           async mount() {
//               const monaco = await loadMonaco();
//               refs.set('model', monaco.editor.createModel('', 'python'));
//               refs.set('editor', monaco.editor.create(this.$refs.editor, {
//                   model: refs.get('model'),
//               }));
//           },
//       };
//   }
//
// Names are pinned at creation: a typo on get/set throws instead of
// silently creating a new slot.  The helper is intentionally tiny —
// its real value is being the only documented way (and grep-able
// landmark) for closure-state in the notebook editor codebase.

export function createClosureRefs(names) {
    const slots = Object.create(null);
    for (const name of names) {
        slots[name] = null;
    }
    const guard = (name) => {
        if (!(name in slots)) {
            throw new Error(`closure-ref slot ${JSON.stringify(name)} not declared in createClosureRefs([...])`);
        }
    };
    return {
        get(name) { guard(name); return slots[name]; },
        set(name, value) { guard(name); slots[name] = value; return value; },
        has(name) { return slots[name] !== null && slots[name] !== undefined; },
    };
}
