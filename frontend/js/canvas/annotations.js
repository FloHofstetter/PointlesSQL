/*
 * Sticky-note annotations for the canvas editor.
 *
 * Free-floating notes dropped onto the canvas surface, persisted in the
 * component's `annotations` array (and saved into the canvas doc's
 * metadata).  Create / update / remove plus the pointer-drag handler.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy;
 * the inner drag / undo callbacks stay arrows so they capture it.
 */

import { findNonOverlappingPosition } from '../dp_canvas/_canvas_helpers.js';

export const annotationMethods = {
  addStickyNote() {
    if (!this.canWrite) return;
    // Spawn at viewport-centre instead of a fixed (60,60) that overlaps
    // freshly auto-laid blocks.  Mirrors the pan-math in
    // searchSelectMatch().
    const df = this._drawflow;
    let cx = 200;
    let cy = 120;
    if (df && typeof df.canvas_x !== 'undefined') {
      const rect = df.container.getBoundingClientRect();
      const zoom = df.zoom || 1;
      cx = Math.round((rect.width / 2 - df.canvas_x) / zoom - 110);
      cy = Math.round((rect.height / 2 - df.canvas_y) / zoom - 60);
    }
    const noteSize = { width: 220, height: 120 };
    // Avoid landing on top of existing nodes or other stickies — slide
    // (+40, +40) up to 8 attempts until the overlap drops below 30 %
    // of the note area.  Helper lives in canvas_shared so mesh can
    // reuse the same collision-avoid pattern later.
    const obstacles = [
      ...Object.values(this.nodes).map((n) => ({
        x: n.position?.x || 0,
        y: n.position?.y || 0,
        width: 200,
        height: 100,
      })),
      ...this.annotations.map((a) => ({
        x: a.x,
        y: a.y,
        width: a.width || 220,
        height: a.height || 120,
      })),
    ];
    const placed = findNonOverlappingPosition({ x: cx, y: cy }, noteSize, obstacles);
    const note = {
      id: 'note-' + Math.random().toString(36).slice(2, 10),
      x: placed.x,
      y: placed.y,
      width: noteSize.width,
      height: noteSize.height,
      content: '',
    };
    this.annotations = [...this.annotations, note];
    this._pushCommand({
      do: () => {
        if (!this.annotations.find((a) => a.id === note.id)) {
          this.annotations = [...this.annotations, note];
        }
      },
      undo: () => {
        this.annotations = this.annotations.filter((a) => a.id !== note.id);
      },
    });
    this._scheduleAutosave();
    this._scheduleMinimapRender();
  },

  updateStickyNote(id, patch) {
    const idx = this.annotations.findIndex((a) => a.id === id);
    if (idx < 0) return;
    this.annotations[idx] = { ...this.annotations[idx], ...patch };
    this.annotations = [...this.annotations];
    this._scheduleAutosave();
  },

  removeStickyNote(id) {
    const snapshot = this.annotations.find((a) => a.id === id);
    this.annotations = this.annotations.filter((a) => a.id !== id);
    if (snapshot) {
      this._pushCommand({
        do: () => {
          this.annotations = this.annotations.filter((a) => a.id !== id);
        },
        undo: () => {
          this.annotations = [...this.annotations, { ...snapshot }];
        },
      });
    }
    this._scheduleAutosave();
    this._scheduleMinimapRender();
  },

  _stickyNotePointerDown(ev, note) {
    if (ev.target.matches('button, textarea')) return;
    ev.preventDefault();
    const startX = ev.clientX;
    const startY = ev.clientY;
    const baseX = note.x;
    const baseY = note.y;
    const onMove = (e) => {
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      this.updateStickyNote(note.id, { x: baseX + dx, y: baseY + dy });
    };
    const onUp = () => {
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
    };
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  },
};
