// Phase 12.7 Sprint 65 — vendored-Monaco AMD loader wrapper.
//
// base.html / notebook_editor.html load `vs/loader.js` synchronously
// before this module imports.  Here we configure `require.paths.vs`
// against the vendored tree and call `require(['vs/editor/editor.main'])`
// after `window` finishes loading — the Sprint-64 BUG-64-03 fix:
// Monaco's AMD loader injects ~30 <script> tags for editor.main /
// basic-languages / themes / NLS bundles, and Firefox keeps `load`
// pending until every last one resolves.  Playwright's
// `page.goto(..., waitUntil:'load')` then times out at 30 s on a
// perfectly-usable page.  Deferring AMD until after `load` lets the
// load event fire immediately (only static scripts pending), then
// Monaco streams in while the user already sees the toolbar with
// "Connecting kernel…" / "Loading Pyright…" pills.

const MONACO_BASE = '/static/js/vendor/monaco/vs';
let monacoReady = null;

export function loadMonaco() {
    if (monacoReady) return monacoReady;
    monacoReady = new Promise((resolve, reject) => {
        const start = () => {
            try {
                if (typeof require !== 'function' || !require.config) {
                    reject(new Error('monaco loader not present — check vendor script'));
                    return;
                }
                require.config({ paths: { vs: MONACO_BASE } });
                require(['vs/editor/editor.main'], () => {
                    if (typeof monaco === 'undefined') {
                        reject(new Error('monaco module loaded but global missing'));
                        return;
                    }
                    resolve(monaco);
                });
            } catch (err) {
                reject(err);
            }
        };
        if (document.readyState === 'complete') {
            start();
        } else {
            window.addEventListener('load', start, { once: true });
        }
    });
    return monacoReady;
}
