// Phase 81.G.B — multi-select state for list/table pages.
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
// Methods:
//   toggleOne(key)              — flip membership
//   selectAll(keys)             — add all
//   clearSelection()            — empty the set
//   isSelected(key) -> bool
//   allSelected(keys) -> bool
//   noneSelected() -> bool
//   selectedCount -> int        (getter)
//   selectedKeys -> string[]    (getter)
//
// Keys are coerced to String on insert so numeric / UUID / composite
// keys all live happily together.

export function bulkSelect() {
    return {
        _selected: new Set(),

        toggleOne(key) {
            const k = String(key);
            if (this._selected.has(k)) this._selected.delete(k);
            else this._selected.add(k);
            // Alpine doesn't auto-react to Set mutations; tickle a
            // reactive flag so :class / x-show re-evaluate.
            this._selectionTick++;
        },

        selectAll(keys) {
            keys.forEach((k) => this._selected.add(String(k)));
            this._selectionTick++;
        },

        clearSelection() {
            this._selected.clear();
            this._selectionTick++;
        },

        isSelected(key) {
            // Read the tick so Alpine tracks the dependency.
            return this._selectionTick >= 0 && this._selected.has(String(key));
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
            return this._selectionTick >= 0 && this._selected.size === 0;
        },

        get selectedCount() {
            return this._selectionTick >= 0 ? this._selected.size : 0;
        },

        get selectedKeys() {
            return this._selectionTick >= 0 ? Array.from(this._selected) : [];
        },

        _selectionTick: 0,
    };
}

// Default-export for ESM imports.  bootstrap.js re-attaches the
// factory to ``window.bulkSelect`` so plain inline Alpine factories
// can spread it without an ES-module import.
export default bulkSelect;
