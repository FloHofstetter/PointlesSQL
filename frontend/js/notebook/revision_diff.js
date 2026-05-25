/**
 * Revision-history diff viewer.
 *
 * Companion installer to `revisions.js`: the list / snapshot /
 * pin-as-fact surface lives there, the diff-pair pick + unified-diff
 * render lives here.  Both mutate the same `state.revisions` object
 * so the panel template only sees one source of truth.
 *
 * Selection model: clicking a list row toggles it as the "left" pin;
 * the next clicked row becomes "right" and triggers
 * `loadRevisionDiff()`.  After the pair is set we normalise it
 * chronologically (older → newer) so the rendered red/green colours
 * read like `git diff old new`.
 */

export function installRevisionDiff(state) {
 // Extend the revisions namespace established by installRevisions
 // with diff-pick + render state slots.
 Object.assign(state.revisions, {
  selectedLeftUuid: null,
  selectedRightUuid: null,
  diff: null,
  diffLoading: false,
  diffError: '',
 });

 /**
  * Two-click selection: first click pins ``left``, second click
  * pins ``right`` and fetches the diff envelope.  Third click
  * resets the pair to start over.
  *
  * After both pins are set the pair is normalised chronologically so
  * L is always the older revision and R the newer one — the diff then
  * reads as "what was added/removed going forward in time", which
  * matches the standard `git diff old new` mental model and makes the
  * red/green colours intuitive.
  */
 state.selectRevisionForDiff = async function (uuid) {
  if (!uuid) return;
  if (!this.revisions.selectedLeftUuid) {
   this.revisions.selectedLeftUuid = uuid;
   this.revisions.diff = null;
   return;
  }
  if (!this.revisions.selectedRightUuid) {
   if (uuid === this.revisions.selectedLeftUuid) {
    this.revisions.selectedLeftUuid = null;
    return;
   }
   const [left, right] = this._orderRevisionsChronologically(
    this.revisions.selectedLeftUuid,
    uuid,
   );
   this.revisions.selectedLeftUuid = left;
   this.revisions.selectedRightUuid = right;
   await this.loadRevisionDiff();
   return;
  }
  this.revisions.selectedLeftUuid = uuid;
  this.revisions.selectedRightUuid = null;
  this.revisions.diff = null;
 };

 /**
  * Swap the L and R pins in place and re-fetch the diff so the user
  * can flip the comparison direction without re-pinning from scratch.
  */
 state.swapRevisionPins = async function () {
  const { selectedLeftUuid, selectedRightUuid } = this.revisions;
  if (!selectedLeftUuid || !selectedRightUuid) return;
  this.revisions.selectedLeftUuid = selectedRightUuid;
  this.revisions.selectedRightUuid = selectedLeftUuid;
  await this.loadRevisionDiff();
 };

 /**
  * Return ``[olderUuid, newerUuid]`` based on the ``created_at`` field
  * already loaded into ``this.revisions.rows``.  Falls back to insert
  * order when timestamps are missing or equal.
  */
 state._orderRevisionsChronologically = function (uuidA, uuidB) {
  const lookup = Object.fromEntries(
   this.revisions.rows.map((r) => [r.revision_uuid, r.created_at || '']),
  );
  const tsA = lookup[uuidA] || '';
  const tsB = lookup[uuidB] || '';
  if (tsA && tsB && tsA !== tsB) {
   return tsA < tsB ? [uuidA, uuidB] : [uuidB, uuidA];
  }
  return [uuidA, uuidB];
 };

 /**
  * Per-cell ``+N / -M`` stats for a Changed entry, derived from the
  * same naive line-diff the rendered block uses so the badge matches
  * what the reader sees.
  */
 state.diffStatsFor = function (entry) {
  const rows = this.renderUnifiedDiff(entry.old.source, entry.new.source);
  let adds = 0;
  let removes = 0;
  for (const row of rows) {
   if (row.kind === 'add') adds++;
   else if (row.kind === 'remove') removes++;
  }
  return { adds, removes };
 };

 state.clearRevisionDiff = function () {
  this.revisions.selectedLeftUuid = null;
  this.revisions.selectedRightUuid = null;
  this.revisions.diff = null;
  this.revisions.diffError = '';
 };

 state.loadRevisionDiff = async function () {
  const { selectedLeftUuid, selectedRightUuid } = this.revisions;
  if (!selectedLeftUuid || !selectedRightUuid) return;
  this.revisions.diffLoading = true;
  this.revisions.diffError = '';
  try {
   const qs = new URLSearchParams({
    left: selectedLeftUuid,
    right: selectedRightUuid,
   });
   const res = await window.pqlApi.fetch(
    `/api/notebooks/revisions/diff?${qs.toString()}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.revisions.diff = res.data;
   } else {
    this.revisions.diffError =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.revisions.diffError = (err && err.message) || String(err);
  } finally {
   this.revisions.diffLoading = false;
  }
 };

 /**
  * Render a naive line-by-line diff between two strings.  Returns
  * an array of ``{kind, text, lnoOld, lnoNew}`` rows the panel paints
  * as a tidy two-column unified-diff block.  Line numbers are 1-based
  * and ``null`` when the row doesn't exist on that side.  Not as smart
  * as Monaco's tokenisation but good enough for cell-source deltas
  * which are usually small.
  */
 state.renderUnifiedDiff = function (oldText, newText) {
  const a = (oldText || '').split('\n');
  const b = (newText || '').split('\n');
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
   endA--;
   endB--;
  }
  const rows = [];
  for (let i = 0; i < start; i++) {
   rows.push({ kind: 'context', text: a[i], lnoOld: i + 1, lnoNew: i + 1 });
  }
  for (let i = start; i < endA; i++) {
   rows.push({ kind: 'remove', text: a[i], lnoOld: i + 1, lnoNew: null });
  }
  for (let i = start; i < endB; i++) {
   rows.push({ kind: 'add', text: b[i], lnoOld: null, lnoNew: i + 1 });
  }
  const tailOffsetNew = endB - endA;
  for (let i = endA; i < a.length; i++) {
   rows.push({
    kind: 'context',
    text: a[i],
    lnoOld: i + 1,
    lnoNew: i + 1 + tailOffsetNew,
   });
  }
  return rows;
 };
}
