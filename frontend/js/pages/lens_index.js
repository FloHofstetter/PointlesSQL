// Auto-extracted from frontend/templates/pages/lens_index.html.
// Exports: lensChat.
//
export function lensChat() {
  return {
    sessions: [],
    activeId: null,
    messages: [],
    draft: '',
    thinking: false,
    async init() {
      await this.loadSessions();
    },
    async loadSessions() {
      const res = await fetch('/api/lens/sessions');
      const body = await res.json();
      this.sessions = body.sessions || [];
    },
    async newSession() {
      const title = prompt('Session title?', 'New analysis');
      if (!title) return;
      const res = await fetch('/api/lens/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title, llm_provider: 'anthropic' }),
      });
      if (res.ok) {
        const body = await res.json();
        await this.loadSessions();
        await this.loadSession(body.id);
      } else {
        alert('Could not create session: ' + res.status);
      }
    },
    async loadSession(id) {
      this.activeId = id;
      const res = await fetch(`/api/lens/sessions/${id}/messages`);
      const body = await res.json();
      this.messages = body.messages || [];
    },
    async deleteSession(id) {
      if (!confirm('Delete this session?')) return;
      await fetch(`/api/lens/sessions/${id}`, { method: 'DELETE' });
      if (this.activeId === id) {
        this.activeId = null;
        this.messages = [];
      }
      await this.loadSessions();
    },
    async sendMessage() {
      if (!this.draft.trim() || !this.activeId) return;
      this.thinking = true;
      try {
        await fetch(`/api/lens/sessions/${this.activeId}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: this.draft }),
        });
        this.draft = '';
        await this.loadSession(this.activeId);
      } finally {
        this.thinking = false;
      }
    },
  };
}
