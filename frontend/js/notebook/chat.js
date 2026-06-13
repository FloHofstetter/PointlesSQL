/**
 * chat-drawer Alpine factory for the notebook editor.
 *
 * Forked from ``frontend/js/sql_editor/chat.js``.  Three deltas:
 *
 *  1. The WS URL targets ``/ws/notebook/chat/{id}``.
 *  2. ``_handleNotify`` consumes ``cell_proposal_created`` /
 *     ``cell_proposal_accepted`` / ``cell_proposal_discarded``
 *     frames (polymorphic — branded on ``action``).
 *  3. Accepting a proposal POSTs to the notebook accept route then
 *     dispatches ``pql:cell-proposal-accepted`` on ``window`` so
 *     the editor's chat-integration mixin can apply the change.
 *     We deliberately avoid an Alpine scope lookup; the
 *     window-level event bus matches the kernel-WS pattern the
 *     editor already uses.
 */

const CHAT_RECONNECT_DELAY_MS = 2000;

/**
 * Build the WS URL for a notebook editor-session-id.
 *
 * @param {string} editorSessionId
 * @param {string} [notebookUuid] Optional notebook UUID forwarded
 *   as ``?notebook_id=…`` so the agent factory can stamp
 *   ``POINTLESSQL_NOTEBOOK_ID`` for the Phase-105.6 plugin
 *   agent-presence wiring.
 * @returns {string}
 */
function buildNotebookChatUrl(editorSessionId, notebookUuid) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const base = `${proto}//${window.location.host}/ws/notebook/chat/${editorSessionId}`;
  if (!notebookUuid) return base;
  return `${base}?notebook_id=${encodeURIComponent(notebookUuid)}`;
}

/**
 * Alpine factory.
 *
 * @param {string} editorSessionId
 * @param {string} [notebookUuid]
 * @returns {object}
 */
export function notebookChatPanel(editorSessionId, notebookUuid) {
  return {
    editorSessionId,
    notebookUuid: notebookUuid || '',
    _ws: /** @type {WebSocket | null} */ (null),
    _reconnectHandle: /** @type {number | null} */ (null),
    _nextRequestId: 1,
    status: 'disconnected',
    statusLabel: 'idle',
    messages: /** @type {Array<{role: string, content: string}>} */ ([]),
    proposals: /** @type {Array<object>} */ ([]),
    prompt: '',
    streaming: false,
    streamingText: '',
    lastError: '',
    // True when the server turned the assistant off by configuration
    // (LLM not configured / assistant disabled) — rendered as a caution
    // rather than a hard error.
    disabled: false,
    currentTurnId: /** @type {string | null} */ (null),

    get proposalCount() {
      return (this.proposals || []).filter((p) => p.action !== 'explain' || !p._dismissed).length;
    },

    /** Open the WebSocket. */
    connect() {
      if (this._ws && this._ws.readyState === WebSocket.OPEN) return;
      this.status = 'connecting';
      this.statusLabel = 'connecting…';
      const ws = new WebSocket(buildNotebookChatUrl(this.editorSessionId, this.notebookUuid));
      this._ws = ws;
      ws.onopen = () => {
        this.status = 'connected';
        this.statusLabel = 'connected';
        this.disabled = false;
      };
      ws.onmessage = (event) => this._handleFrame(event.data);
      ws.onerror = () => {
        this.status = 'error';
        this.statusLabel = 'connection error';
      };
      ws.onclose = (event) => this._handleClose(event);
    },

    /** Disconnect cleanly. */
    disconnect() {
      if (this._reconnectHandle !== null) {
        clearTimeout(this._reconnectHandle);
        this._reconnectHandle = null;
      }
      if (this._ws) {
        try {
          this._ws.close();
        } catch (_e) {
          /* swallow */
        }
        this._ws = null;
      }
    },

    /** Send the current prompt; clears the input afterwards. */
    send() {
      const text = this.prompt.trim();
      if (!text || this.streaming) return;
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) {
        this.lastError = 'Chat is not connected; reload to reconnect.';
        return;
      }
      this.streaming = true;
      this.streamingText = '';
      this.statusLabel = 'thinking…';
      this.lastError = '';
      const id = this._nextRequestId++;
      this._ws.send(JSON.stringify({ id, method: 'prompt', params: { text } }));
      this.messages.push({ role: 'user', content: text });
      this.prompt = '';
      this._scrollToBottom();
    },

    /** Cancel the in-flight turn. */
    cancel() {
      if (!this._ws || !this.streaming) return;
      const id = this._nextRequestId++;
      this._ws.send(JSON.stringify({ id, method: 'cancel' }));
    },

    /** Reset the server-side conversation. */
    reset() {
      this.messages = [];
      this.proposals = [];
      this.streamingText = '';
      this.lastError = '';
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      const id = this._nextRequestId++;
      this._ws.send(JSON.stringify({ id, method: 'reset' }));
    },

    /** Discard a proposal — server flips status; WS fan-out clears local. */
    async discardProposal(proposal) {
      const id = proposal.proposal_id;
      try {
        await window.pqlApi.fetch(`/api/notebook/chat/proposals/${id}/discard`, {
          method: 'POST',
          silent: true,
        });
      } catch (_e) {
        /* swallow — proposal may already be in a terminal state */
      }
      this._removeProposalLocal(id);
    },

    /**
     * Accept a propose/fix proposal: server flips status, then we
     * dispatch a window event so the editor's chat-integration
     * mixin can apply the change.
     */
    async acceptProposal(proposal) {
      const id = proposal.proposal_id;
      const result = await window.pqlApi.fetch(`/api/notebook/chat/proposals/${id}/accept`, {
        method: 'POST',
        silent: true,
      });
      if (!result.ok) {
        this.lastError = (result.data && result.data.detail) || 'failed to accept proposal';
        return;
      }
      window.dispatchEvent(
        new CustomEvent('pql:cell-proposal-accepted', {
          detail: result.data,
        })
      );
      this._removeProposalLocal(id);
    },

    _removeProposalLocal(id) {
      this.proposals = this.proposals.filter((p) => p.proposal_id !== id);
    },

    _handleFrame(text) {
      let frame;
      try {
        frame = JSON.parse(text);
      } catch (_e) {
        return;
      }
      if (frame.notify) {
        this._handleNotify(frame.notify, frame.params || {});
        return;
      }
      if (frame.error) {
        this.lastError = frame.error.message || 'chat error';
        this.streaming = false;
        this.statusLabel = 'error';
        return;
      }
      // ``{"id":..., "result": ...}`` — turn acknowledged.
    },

    _handleNotify(kind, params) {
      switch (kind) {
        case 'ready':
          this.statusLabel = 'connected';
          if (Array.isArray(params.history)) {
            this.messages = params.history
              .filter((m) => m && (m.role === 'user' || m.role === 'assistant'))
              .map((m) => ({
                role: m.role,
                content: String(m.content || ''),
              }));
          }
          break;
        case 'token':
          this.streamingText += String(params.text || '');
          this._scrollToBottom();
          break;
        case 'tool_phase':
          this.statusLabel = 'calling tool…';
          break;
        case 'cell_proposal_created':
          this.proposals.push({
            proposal_id: String(params.proposal_id),
            action: String(params.action || 'propose'),
            cell_type: params.cell_type || null,
            target_cell_uuid: params.target_cell_uuid || null,
            new_source: params.new_source || null,
            explanation: params.explanation || null,
            position_after_cell_uuid: params.position_after_cell_uuid || null,
            position_at_end: !!params.position_at_end,
            rationale: params.rationale || null,
            auto_accepted: !!params.auto_accepted,
            agent_run_id: params.agent_run_id || null,
          });
          break;
        case 'cell_proposal_accepted':
          // Server-side accept echo — clear the banner.
          this._removeProposalLocal(params.proposal_id);
          break;
        case 'cell_proposal_discarded':
          this._removeProposalLocal(params.proposal_id);
          break;
        case 'final':
          this.streaming = false;
          this.statusLabel = 'connected';
          if (params.text) {
            this.messages.push({
              role: 'assistant',
              content: String(params.text),
            });
          }
          this.streamingText = '';
          this._scrollToBottom();
          break;
        case 'cancelled':
          this.streaming = false;
          this.statusLabel = 'cancelled';
          this.streamingText = '';
          break;
        case 'error':
          this.streaming = false;
          this.lastError = String(params.detail || 'chat error');
          this.statusLabel = 'error';
          break;
      }
    },

    _handleClose(event) {
      this.status = 'disconnected';
      if (event.code === 1011 && event.reason === 'LLM_NOT_CONFIGURED') {
        this.statusLabel = 'LLM not configured';
        this.disabled = true;
        this.lastError =
          'No LLM provider is configured on the server. Set ANTHROPIC_API_KEY (or another supported env var) and reload.';
        return;
      }
      if (event.code === 4503) {
        this.statusLabel = 'AI assistant disabled';
        this.disabled = true;
        this.lastError = 'The AI Assistant is disabled on this deployment.';
        return;
      }
      if (event.code === 4401) {
        this.statusLabel = 'sign-in required';
        this.lastError = 'Your session expired — reload the page to sign in again.';
        return;
      }
      this.statusLabel = 'reconnecting…';
      this._reconnectHandle = window.setTimeout(() => this.connect(), CHAT_RECONNECT_DELAY_MS);
    },

    _scrollToBottom() {
      this.$nextTick(() => {
        if (!this.$refs.messageList) return;
        this.$refs.messageList.scrollTop = this.$refs.messageList.scrollHeight;
      });
    },
  };
}
