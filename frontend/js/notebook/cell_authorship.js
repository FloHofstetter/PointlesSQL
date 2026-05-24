/**
 * Per-cell authorship attribution.
 *
 * Loads ``{cell_uuid -> envelope}`` for the whole notebook once on
 * mount + after every save, then exposes ``attributionFor(cell)`` as
 * a synchronous lookup the cell-header chip template binds to.
 *
 * Pattern matches ``./notebook_tags.js`` — fields + methods mixed
 * onto the editor state via ``installCellAuthorship(state)`` so the
 * template stays declarative and no nested-x-data factory is needed
 * (avoiding the ``feedback_alpine_root_inside_nested_xdata`` trap).
 */

export function installCellAuthorship(state) {
 state.cellAttributions = {};

 /**
  * Fetch ``{cell_uuid: envelope}`` for this notebook in one round
  * trip.  Failures are non-fatal — the chip simply renders nothing
  * for cells without an entry.
  */
 state.loadCellAttributions = async function () {
  if (!this.path) return;
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/attribution/bulk?path=${encodeURIComponent(this.path)}`,
    { silent: true },
   );
   if (res.ok && res.data && res.data.attributions) {
    this.cellAttributions = res.data.attributions;
   }
  } catch {
   // Non-fatal — leave the prior snapshot in place.
  }
 };

 /**
  * Synchronous lookup for the cell-header chip template.
  *
  * Returns the envelope or ``null`` so the chip can ``x-show`` cleanly.
  */
 state.attributionFor = function (cell) {
  if (!cell || !cell.cell_uuid) return null;
  return this.cellAttributions[cell.cell_uuid] || null;
 };

 /**
  * Whether the per-cell author chip should paint at all.
  *
  * Suppresses the chip when the only contributor IS the viewing user
  * (single-author notebook in their own workspace): the email of both
  * ``first_author`` and ``last_modifier`` matches ``currentUser.email``
  * and no agent ever touched the cell.  That is the default-state
  * case the plan flagged — chips should surface deltas from default,
  * not echo "you wrote this" on every cell.
  *
  * Agent-authored or mixed-author cells still paint normally.
  */
 state.shouldShowAuthorChip = function (cell) {
  const attr = this.attributionFor(cell);
  if (!attr) return false;
  const viewer = (this.currentUser && this.currentUser.email) || '';
  if (!viewer) return true;
  const first = attr.first_author || {};
  const last = attr.last_modifier || {};
  const allHuman =
   first.kind !== 'agent' && (!last.kind || last.kind !== 'agent');
  if (!allHuman) return true;
  const firstEmail = (first.email || '').toLowerCase();
  const lastEmail = (last.email || firstEmail || '').toLowerCase();
  const viewerEmail = viewer.toLowerCase();
  return !(firstEmail === viewerEmail && lastEmail === viewerEmail);
 };

 /**
  * Format the chip label.  Compresses ``first.last@org`` to the
  * local-part — full mail goes into the tooltip via :title.
  */
 state.authorChipLabel = function (cell) {
  const attr = this.attributionFor(cell);
  if (!attr) return '';
  const first = attr.first_author || {};
  const last = attr.last_modifier || {};
  const firstLabel = _shortAuthor(first);
  const lastLabel = _shortAuthor(last);
  if (!firstLabel) return '';
  if (lastLabel && lastLabel !== firstLabel) {
   return `${firstLabel} → ${lastLabel}`;
  }
  return firstLabel;
 };

 /**
  * Tooltip text — full email + agent id + created/modified
  * timestamps if both differ.
  */
 state.authorChipTooltip = function (cell) {
  const attr = this.attributionFor(cell);
  if (!attr) return '';
  const first = attr.first_author || {};
  const last = attr.last_modifier || {};
  const parts = [];
  const firstFull = _fullAuthor(first);
  const lastFull = _fullAuthor(last);
  if (firstFull) parts.push(`Minted by ${firstFull}`);
  if (lastFull && lastFull !== firstFull) {
   parts.push(`Last edit by ${lastFull}`);
  }
  if (attr.created_at) parts.push(`Created: ${attr.created_at}`);
  if (attr.last_modified_at && attr.last_modified_at !== attr.created_at) {
   parts.push(`Modified: ${attr.last_modified_at}`);
  }
  return parts.join(' • ');
 };

 /**
  * Icon class — bot-icon for agent-kind, person-icon for user.
  * Returned to the template as a string so the binding stays simple.
  */
 state.authorChipIcon = function (cell) {
  const attr = this.attributionFor(cell);
  if (!attr) return 'bi-person';
  const kind = (attr.first_author || {}).kind;
  return kind === 'agent' ? 'bi-robot' : 'bi-person';
 };
}

function _shortAuthor(author) {
 if (!author) return '';
 if (author.kind === 'agent') {
  if (author.agent_id) return `agent#${author.agent_id}`;
  if (author.agent_run_id) return 'AI';
  return 'AI';
 }
 if (author.email) {
  const at = author.email.indexOf('@');
  return at > 0 ? author.email.slice(0, at) : author.email;
 }
 return '';
}

function _fullAuthor(author) {
 if (!author) return '';
 if (author.kind === 'agent') {
  if (author.agent_id) return `Agent ${author.agent_id}`;
  return 'AI assistant';
 }
 return author.email || '';
}
