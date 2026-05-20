/**
 * Notebook widgets panel (Phase 99 UI).
 *
 * Backend (``NotebookWidget`` + REST + 12 pytest) shipped in Phase
 * 99.  This mixin manages a CRUD panel for the parameter widgets:
 * dropdown / slider / text.  Resolving the kernel-visible values
 * via ``POST /api/notebooks/widgets/resolve`` is exposed here too;
 * the kernel-side ``pql.widgets`` shim that consumes them is still
 * on the deferred list.
 */

const KINDS = ['dropdown', 'slider', 'text'];

function blankDraft() {
 return {
  name: '',
  widget_kind: 'text',
  label: '',
  config_raw: '{}',
  default_value_raw: '',
  position: 0,
  error: '',
 };
}

export function installWidgetsPanel(state) {
 state.widgetsPanel = {
  open: false,
  widgets: [],
  loaded: false,
  loading: false,
  submitting: false,
  error: '',
  kinds: KINDS,
  draft: blankDraft(),
  editingName: '',
  resolvedValues: {},
 };

 state.toggleWidgetsPanel = async function () {
  this.widgetsPanel.open = !this.widgetsPanel.open;
  if (this.widgetsPanel.open && !this.widgetsPanel.loaded) {
   await this.loadWidgets();
  }
 };

 state.loadWidgets = async function () {
  if (!this.path) return;
  this.widgetsPanel.loading = true;
  this.widgetsPanel.error = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/widgets?path=${encodeURIComponent(this.path)}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.widgetsPanel.widgets = res.data.widgets || [];
    this.widgetsPanel.loaded = true;
    await this.resolveWidgetValues();
   } else {
    this.widgetsPanel.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.widgetsPanel.error = (err && err.message) || String(err);
  } finally {
   this.widgetsPanel.loading = false;
  }
 };

 state.resolveWidgetValues = async function () {
  try {
   const res = await window.pqlApi.fetch(
    '/api/notebooks/widgets/resolve',
    { method: 'POST', body: { path: this.path } },
   );
   if (res.ok && res.data) {
    this.widgetsPanel.resolvedValues = res.data.values || {};
   }
  } catch {
   // Non-fatal — leave the prior snapshot in place.
  }
 };

 /**
  * Switch the draft to "edit existing" mode by populating fields
  * from an existing widget row.
  */
 state.editWidgetDraft = function (widget) {
  this.widgetsPanel.editingName = widget.name;
  this.widgetsPanel.draft = {
   name: widget.name,
   widget_kind: widget.widget_kind,
   label: widget.label,
   config_raw: JSON.stringify(widget.config || {}, null, 2),
   default_value_raw:
    widget.default_value === null || widget.default_value === undefined
     ? ''
     : JSON.stringify(widget.default_value),
   position: widget.position || 0,
   error: '',
  };
 };

 state.resetWidgetDraft = function () {
  this.widgetsPanel.editingName = '';
  this.widgetsPanel.draft = blankDraft();
 };

 /**
  * Submit the draft via ``PUT /api/notebooks/widgets``.  Empty
  * default_value_raw is sent as ``null``; non-empty is parsed as
  * JSON so the server sees the right type.
  */
 state.submitWidget = async function () {
  if (this.widgetsPanel.submitting) return;
  const d = this.widgetsPanel.draft;
  d.error = '';
  if (!d.name.trim() || !d.label.trim()) {
   d.error = 'name and label are required';
   return;
  }
  if (!KINDS.includes(d.widget_kind)) {
   d.error = `widget_kind must be one of ${KINDS.join(', ')}`;
   return;
  }
  let config;
  try {
   config = JSON.parse(d.config_raw || '{}');
   if (!config || typeof config !== 'object' || Array.isArray(config)) {
    throw new Error('config must be a JSON object');
   }
  } catch (err) {
   d.error = `config: ${(err && err.message) || String(err)}`;
   return;
  }
  let defaultValue = null;
  if (d.default_value_raw && d.default_value_raw.trim()) {
   try {
    defaultValue = JSON.parse(d.default_value_raw);
   } catch (err) {
    d.error = `default_value: ${(err && err.message) || String(err)}`;
    return;
   }
  }
  this.widgetsPanel.submitting = true;
  try {
   const res = await window.pqlApi.fetch('/api/notebooks/widgets', {
    method: 'PUT',
    body: {
     path: this.path,
     name: d.name.trim(),
     widget_kind: d.widget_kind,
     label: d.label.trim(),
     config,
     default_value: defaultValue,
     position: Number(d.position) || 0,
    },
   });
   if (!res.ok) {
    d.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   this.resetWidgetDraft();
   await this.loadWidgets();
  } catch (err) {
   d.error = (err && err.message) || String(err);
  } finally {
   this.widgetsPanel.submitting = false;
  }
 };

 state.deleteWidget = async function (widget) {
  if (!widget || !widget.name) return;
  if (this.widgetsPanel.submitting) return;
  this.widgetsPanel.submitting = true;
  this.widgetsPanel.error = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/widgets?path=${encodeURIComponent(this.path)}&name=${encodeURIComponent(widget.name)}`,
    { method: 'DELETE' },
   );
   if (!res.ok) {
    this.widgetsPanel.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   if (this.widgetsPanel.editingName === widget.name) {
    this.resetWidgetDraft();
   }
   await this.loadWidgets();
  } catch (err) {
   this.widgetsPanel.error = (err && err.message) || String(err);
  } finally {
   this.widgetsPanel.submitting = false;
  }
 };
}
