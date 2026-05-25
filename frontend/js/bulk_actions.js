// multi-select state for list/table pages.
//
// Tiny Alpine mixin that any page can spread into its x-data
// factory to gain a checkbox column + bulk-action toolbar:
//
//     return { ...bulkSelect(), rows: [...], async loadRows() {...} }
//
// The mixin owns nothing but a Set of keys; the page decides what
// the keys mean (alert slug, anomaly composite key, issue id, …)
// and which bulk action(s) to expose.
//
// Properties:
//   selectedCount       — int (reactive)
//   selectedKeys        — string[] (reactive)
// Methods:
//   toggleOne(key)
//   selectAll(keys)
//   clearSelection()
//   isSelected(key) -> bool
//   allSelected(keys) -> bool
//   toggleAllVisible(keys)
//   noneSelected() -> bool
//
// Implementation note: ``selectedCount`` and ``selectedKeys`` are
// kept as plain reactive own-properties (not getters).  The spread
// operator (``...bulkSelect()``) evaluates getters at spread time
// and stores the result as a static value — so a naive getter
// implementation would always read 0.  Keeping them as values that
// toggleOne / selectAll / clearSelection maintain in lock-step
// sidesteps the spread trap and gives Alpine straightforward
// reactivity tracking.
//
// Keys are coerced to String on insert so numeric / UUID /
// composite keys all live happily together.

export function bulkSelect() {
  return {
    _selected: new Set(),
    selectedCount: 0,
    selectedKeys: [],

    _sync() {
      this.selectedCount = this._selected.size;
      this.selectedKeys = Array.from(this._selected);
    },

    toggleOne(key) {
      const k = String(key);
      if (this._selected.has(k)) this._selected.delete(k);
      else this._selected.add(k);
      this._sync();
    },

    selectAll(keys) {
      keys.forEach((k) => {
        this._selected.add(String(k));
      });
      this._sync();
    },

    clearSelection() {
      this._selected.clear();
      this._sync();
    },

    isSelected(key) {
      // Read selectedCount so Alpine tracks the dependency
      // (Set membership isn't reactive on its own).
      return this.selectedCount >= 0 && this._selected.has(String(key));
    },

    allSelected(keys) {
      if (!keys || !keys.length) return false;
      return keys.every((k) => this._selected.has(String(k)));
    },

    toggleAllVisible(keys) {
      if (this.allSelected(keys)) this.clearSelection();
      else this.selectAll(keys);
    },

    noneSelected() {
      return this.selectedCount === 0;
    },
  };
}

// Default-export for ESM imports.  bootstrap.js re-attaches the
// factory to ``window.bulkSelect`` so plain inline Alpine factories
// can spread it without an ES-module import.
export default bulkSelect;
