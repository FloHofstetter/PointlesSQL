/**
 * Phase 96 — notebook AI-assistant chat integration mixin.
 *
 * Installed onto the ``notebookEditor`` Alpine state after the
 * other mixins so it can call ``insertCellFromProposal`` /
 * ``updateCellSourceByUuid`` (added in cell_operations.js) and
 * read/write ``_pendingProvenance`` consumed by persistence.js.
 *
 * Cross-component talk uses ``window.dispatchEvent`` with the
 * custom event ``pql:cell-proposal-accepted`` so the chat panel
 * factory and the editor never share an Alpine scope — keeps the
 * panel's WS lifecycle isolated from the editor's reactive state.
 */

export function installChatIntegration(state) {
  state.toggleChatPanel = function () {
    this.chatPanelOpen = !this.chatPanelOpen;
  };

  state._applyAcceptedProposal = async function (payload) {
    if (!payload || typeof payload !== 'object') return;
    const action = payload.action;
    if (action === 'propose') {
      await this.insertCellFromProposal({
        afterCellUuid: payload.position_after_cell_uuid,
        atEnd: !!payload.position_at_end,
        cellType: payload.cell_type,
        source: payload.new_source,
        proposalId: payload.proposal_id,
        agentRunId: payload.agent_run_id,
      });
    } else if (action === 'fix') {
      await this.updateCellSourceByUuid(
        payload.target_cell_uuid,
        payload.new_source,
        {
          proposalId: payload.proposal_id,
          agentRunId: payload.agent_run_id,
        },
      );
    }
    // ``explain`` proposals auto-accept on the server and don't
    // mutate cells — the social-drawer Explanations tab picks them
    // up via its own fetch, no editor action needed.
  };

  state._installChatProposalListener = function () {
    if (this._onCellProposalAccepted) return;
    this._onCellProposalAccepted = (ev) => {
      const detail = ev && ev.detail;
      if (!detail) return;
      this._applyAcceptedProposal(detail);
    };
    window.addEventListener(
      'pql:cell-proposal-accepted',
      this._onCellProposalAccepted,
    );
  };

  state._removeChatProposalListener = function () {
    if (!this._onCellProposalAccepted) return;
    window.removeEventListener(
      'pql:cell-proposal-accepted',
      this._onCellProposalAccepted,
    );
    this._onCellProposalAccepted = null;
  };
}
