/*
 * Undo / redo command stack for the canvas editor.
 *
 * A command is a `{ do, undo }` pair the mutating gestures (node create /
 * delete / paste …) push onto the stack; this bundle is the generic
 * stack the editor factory composes onto its Alpine component.
 *
 * Methods are plain (never arrow) so `this` resolves to the Alpine proxy
 * at call time when spread into the returned component object.
 */

export const historyMethods = {
  _pushCommand(cmd) {
    this._undoStack.push(cmd);
    if (this._undoStack.length > this._UNDO_DEPTH) this._undoStack.shift();
    this._redoStack = [];
  },

  undo() {
    const cmd = this._undoStack.pop();
    if (!cmd) return;
    try {
      cmd.undo();
      this._redoStack.push(cmd);
    } catch (_e) {
      // Swallow — best-effort restore.
    }
  },

  redo() {
    const cmd = this._redoStack.pop();
    if (!cmd) return;
    try {
      cmd.do();
      this._undoStack.push(cmd);
    } catch (_e) {
      // Swallow.
    }
  },
};
