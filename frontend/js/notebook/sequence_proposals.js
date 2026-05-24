/**
 * Cell-sequence proposals inbox.
 *
 * Backend (``NotebookCellSequenceProposal`` + 10 pytest) shipped in
 * The LLM tool that *creates* sequence proposals lives
 * in the hermes plugin and is deferred — until it lands, the inbox
 * stays empty.  Once it ships, the plugin will fire a
 * ``pql:cell-sequence-proposed`` window event whose ``detail`` is
 * the proposal envelope from
 * ``POST /api/notebook/chat/{chat_session_id}/propose-sequence``.
 *
 * The inbox surfaces all pending proposals; accept inserts every
 * cell at the bottom of the notebook and POSTs to
 * ``/api/notebook/chat/sequences/{proposal_id}/accept``.  Discard
 * just flips the row's status.
 *
 * UI lives outside the chat drawer so a user can dismiss the chat
 * panel without losing in-flight sequence drafts.
 */

export function installSequenceProposals(state) {
 state.sequenceProposals = {
  open: false,
  pending: [],
  busyId: '',
  error: '',
  // Track the listener so we can detach on destroy().
  _listener: null,
 };

 state.toggleSequenceProposals = function () {
  this.sequenceProposals.open = !this.sequenceProposals.open;
 };

 /**
  * Wire the window event listener on init.  Idempotent.
  */
 state._installSequenceListener = function () {
  if (this.sequenceProposals._listener) return;
  const handler = (ev) => {
   const detail = ev && ev.detail;
   if (!detail || !detail.proposal_id) return;
   // Replace if same proposal_id already pending; else prepend.
   const idx = this.sequenceProposals.pending.findIndex(
    (p) => p.proposal_id === detail.proposal_id,
   );
   if (idx >= 0) {
    this.sequenceProposals.pending.splice(idx, 1, detail);
   } else {
    this.sequenceProposals.pending.unshift(detail);
   }
   // Auto-open the drawer the first time something lands.
   if (!this.sequenceProposals.open && this.sequenceProposals.pending.length === 1) {
    this.sequenceProposals.open = true;
   }
  };
  this.sequenceProposals._listener = handler;
  window.addEventListener('pql:cell-sequence-proposed', handler);
 };

 state._removeSequenceListener = function () {
  if (!this.sequenceProposals._listener) return;
  window.removeEventListener(
   'pql:cell-sequence-proposed',
   this.sequenceProposals._listener,
  );
  this.sequenceProposals._listener = null;
 };

 /**
  * Accept one proposal: insert every cell at the end of the
  * notebook, then POST accept.  Refuses to run twice on the same
  * proposal_id (``busyId`` gate).
  */
 state.acceptSequenceProposal = async function (proposal) {
  if (!proposal || !proposal.proposal_id) return;
  if (this.sequenceProposals.busyId) return;
  this.sequenceProposals.busyId = proposal.proposal_id;
  this.sequenceProposals.error = '';
  try {
   const cells = (proposal.cells || []).slice().sort(
    (a, b) => (a.position || 0) - (b.position || 0),
   );
   for (const cell of cells) {
    await this.insertCellFromProposal({
     atEnd: true,
     cellType: cell.cell_type || 'code',
     source: cell.source || '',
     proposalId: proposal.proposal_id,
    });
   }
   const res = await window.pqlApi.fetch(
    `/api/notebook/chat/sequences/${encodeURIComponent(proposal.proposal_id)}/accept`,
    { method: 'POST' },
   );
   if (!res.ok) {
    this.sequenceProposals.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   this.sequenceProposals.pending = this.sequenceProposals.pending.filter(
    (p) => p.proposal_id !== proposal.proposal_id,
   );
  } catch (err) {
   this.sequenceProposals.error = (err && err.message) || String(err);
  } finally {
   this.sequenceProposals.busyId = '';
  }
 };

 /**
  * Discard one proposal — POSTs the terminal status + drops the row
  * from the local list.
  */
 state.discardSequenceProposal = async function (proposal) {
  if (!proposal || !proposal.proposal_id) return;
  if (this.sequenceProposals.busyId) return;
  this.sequenceProposals.busyId = proposal.proposal_id;
  this.sequenceProposals.error = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebook/chat/sequences/${encodeURIComponent(proposal.proposal_id)}/discard`,
    { method: 'POST' },
   );
   if (!res.ok) {
    this.sequenceProposals.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   this.sequenceProposals.pending = this.sequenceProposals.pending.filter(
    (p) => p.proposal_id !== proposal.proposal_id,
   );
  } catch (err) {
   this.sequenceProposals.error = (err && err.message) || String(err);
  } finally {
   this.sequenceProposals.busyId = '';
  }
 };
}
