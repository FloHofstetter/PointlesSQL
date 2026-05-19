/**
 * Phase 91 — chat-drawer Alpine factory for the SQL editor.
 *
 * Owns the WebSocket lifecycle, message buffer, and the
 * proposal-banner queue.  The outer ``sqlEditor()`` scope exposes
 * ``chatOpen`` + ``_chatSessionId``; ``chatPanel()`` reads the
 * session id from a template parameter rather than the parent so
 * the partial stays standalone.
 */

const CHAT_RECONNECT_DELAY_MS = 2000;

/**
 * Build the WS URL for an editor-session-id; supports http/https/dev.
 *
 * @param {string} editorSessionId
 * @returns {string}
 */
function buildChatUrl(editorSessionId) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws/sql/chat/${editorSessionId}`;
}

/**
 * Alpine factory.
 *
 * @param {string} editorSessionId
 * @returns {object}
 */
export function chatPanel(editorSessionId) {
  return {
    editorSessionId,
    _ws: /** @type {WebSocket | null} */ (null),
    _reconnectHandle: /** @type {number | null} */ (null),
    _nextRequestId: 1,
    status: 'disconnected',
    statusLabel: 'idle',
    messages: /** @type {Array<{role: string, content: string}>} */ ([]),
    proposals: /** @type {Array<{proposal_id: string, sql: string, kind: string, rationale: string | null}>} */ ([]),
    prompt: '',
    streaming: false,
    streamingText: '',
    lastError: '',
    currentTurnId: /** @type {string | null} */ (null),

    /** Open the WebSocket. */
    connect() {
      if (this._ws && this._ws.readyState === WebSocket.OPEN) return;
      this.status = 'connecting';
      this.statusLabel = 'connecting…';
      const ws = new WebSocket(buildChatUrl(this.editorSessionId));
      this._ws = ws;
      ws.onopen = () => {
        this.status = 'connected';
        this.statusLabel = 'connected';
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
      this._ws.send(
        JSON.stringify({ id, method: 'prompt', params: { text } }),
      );
      this.messages.push({ role: 'user', content: text });
      this.prompt = '';
      this._scrollToBottom();
    },

    /** Ask the LLM to refine the last failed/empty result. */
    refine(hint, lastSql, lastError) {
      if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
      this.streaming = true;
      this.streamingText = '';
      this.statusLabel = 'refining…';
      this.lastError = '';
      const id = this._nextRequestId++;
      this._ws.send(
        JSON.stringify({
          id,
          method: 'refine',
          params: {
            hint,
            last_sql: lastSql || '',
            last_error: lastError || '',
          },
        }),
      );
      // The server templates a user-message and runs a normal turn;
      // mark the synthetic message in the local history so the user
      // sees what was sent.
      this.messages.push({
        role: 'user',
        content: `(refine: ${hint})`,
      });
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

    /** Discard a proposal — server flips status, WS notify fans out. */
    async discardProposal(proposal) {
      const id = proposal.proposal_id;
      try {
        await window.pqlApi.fetch(
          `/api/sql/chat/proposals/${id}/discard`,
          { method: 'POST', silent: true },
        );
      } catch (_e) {
        /* swallow — the row may already be in a terminal state */
      }
      this._removeProposalLocal(id);
    },

    /** Accept the proposal, load SQL into editor with the chat run id. */
    async loadProposalIntoEditor(proposal) {
      const id = proposal.proposal_id;
      const result = await window.pqlApi.fetch(
        `/api/sql/chat/proposals/${id}/accept`,
        { method: 'POST', silent: true },
      );
      if (!result.ok) {
        this.lastError =
          (result.data && result.data.detail) || 'failed to accept proposal';
        return;
      }
      if (typeof this.$root.setSQL === 'function') {
        this.$root.setSQL(result.data.sql);
      }
      // Stamp the chat run id on the editor so the next Run click
      // sends ``X-Agent-Run-Id`` against the chat run.
      this.$root._chatAgentRunId = result.data.agent_run_id;
      this._removeProposalLocal(id);
      this.$root.chatOpen = false;
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
      // ``{"id":..., "result": ...}`` — turn acknowledged; nothing to render.
    },

    _handleNotify(kind, params) {
      switch (kind) {
        case 'ready':
          this.statusLabel = 'connected';
          if (Array.isArray(params.history)) {
            this.messages = params.history
              .filter((m) => m && (m.role === 'user' || m.role === 'assistant'))
              .map((m) => ({ role: m.role, content: String(m.content || '') }));
          }
          break;
        case 'token':
          this.streamingText += String(params.text || '');
          this._scrollToBottom();
          break;
        case 'tool_phase':
          this.statusLabel = 'calling tool…';
          break;
        case 'proposal_created':
          this.proposals.push({
            proposal_id: String(params.proposal_id),
            sql: String(params.sql || ''),
            kind: String(params.kind || 'dml'),
            rationale: params.rationale || null,
          });
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
      // 1011 + LLM_NOT_CONFIGURED → don't reconnect; surface a helpful error.
      if (event.code === 1011 && event.reason === 'LLM_NOT_CONFIGURED') {
        this.statusLabel = 'LLM not configured';
        this.lastError =
          'No LLM provider is configured on the server. Set ANTHROPIC_API_KEY (or another supported env var) and reload.';
        return;
      }
      this.statusLabel = 'reconnecting…';
      this._reconnectHandle = window.setTimeout(
        () => this.connect(),
        CHAT_RECONNECT_DELAY_MS,
      );
    },

    _scrollToBottom() {
      this.$nextTick(() => {
        if (!this.$refs.messageList) return;
        this.$refs.messageList.scrollTop =
          this.$refs.messageList.scrollHeight;
      });
    },
  };
}

