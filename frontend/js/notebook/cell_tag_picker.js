/**
 * Cell-tag picker — UI state slice.
 *
 * Returns the picker's local state (open / customMode / customDraft)
 * plus the dropdown-toggle helper.  Spread into the cellThread()
 * factory's return so the picker shares the live reactive scope
 * (a separately-nested x-data received a snapshotted `cell` POJO
 * instead — mutations never reached the parent).
 *
 * Tag mutations themselves live as inline expressions in
 * ``cell_tag_picker.html`` so they reference the live x-for ``cell``
 * variable directly; only the UI affordances live here.
 */

export function cellTagPickerSlice() {
  return {
    pickerOpen: false,
    pickerCustomMode: false,
    pickerCustomDraft: '',

    togglePickerOpen() {
      this.pickerOpen = !this.pickerOpen;
      if (!this.pickerOpen) {
        this.pickerCustomMode = false;
        this.pickerCustomDraft = '';
      }
    },
  };
}
