/*
 * Shared Shift+F focus-mode wiring for the canvas surfaces.
 *
 * The editor, mesh and diff pages each toggle a body-level focus mode
 * (chrome hidden, canvas maximised) through the same Shift+F shortcut and
 * the `window.pqlToggleFocusMode` pivot defined in base.html.  This reads
 * the persisted initial state onto the host and binds the one keydown
 * handler all three used to copy verbatim.
 */

/**
 * Wire the Shift+F focus-mode shortcut onto an Alpine host.
 *
 * Sets `host.focusMode` from the persisted flag, then binds a window
 * keydown handler that toggles it via `window.pqlToggleFocusMode`,
 * ignoring keystrokes typed into form fields or editors.
 *
 * @param {{focusMode: boolean}} host - the Alpine component to drive.
 * @param {{formSelector?: string}} [opts] - selector for inputs to ignore.
 * @returns {() => void} teardown that removes the keydown listener.
 */
export function installFocusModeShortcut(host, opts = {}) {
  const formSelector = opts.formSelector || 'input, textarea, .cm-editor';
  try {
    host.focusMode = localStorage.getItem('pql.focus-mode') === '1';
  } catch (_e) {
    host.focusMode = false;
  }
  const handler = (ev) => {
    if (ev.shiftKey && (ev.key === 'F' || ev.key === 'f') && !ev.target.closest(formSelector)) {
      ev.preventDefault();
      if (typeof window.pqlToggleFocusMode === 'function') {
        host.focusMode = window.pqlToggleFocusMode();
      }
    }
  };
  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}
