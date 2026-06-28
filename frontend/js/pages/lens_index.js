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
    newTitle: 'New analysis',
    creating: false,
    createError: null,
    async init() {
      await this.loadSessions();
    },
    async loadSessions() {
      const res = await fetch('/api/lens/sessions');
      const body = await res.json();
      this.sessions = body.sessions || [];
    },
    openNewSession() {
      this.newTitle = 'New analysis';
      this.createError = null;
      const el = document.getElementById('lens-new-modal');
      if (el && window.bootstrap) {
        window.bootstrap.Modal.getOrCreateInstance(el).show();
      }
    },
    async createSession() {
      const title = this.newTitle.trim();
      if (!title) {
        this.createError = 'Please enter a session title.';
        return;
      }
      this.creating = true;
      this.createError = null;
      try {
        const res = await fetch('/api/lens/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: title, llm_provider: 'anthropic' }),
        });
        if (!res.ok) {
          this.createError = `Could not create session (HTTP ${res.status}).`;
          return;
        }
        const body = await res.json();
        const el = document.getElementById('lens-new-modal');
        if (el && window.bootstrap) {
          window.bootstrap.Modal.getInstance(el)?.hide();
        }
        await this.loadSessions();
        await this.loadSession(body.id);
      } catch (e) {
        this.createError = `Could not create session: ${e && e.message ? e.message : e}`;
      } finally {
        this.creating = false;
      }
    },
    async loadSession(id) {
      this.activeId = id;
      const res = await fetch(`/api/lens/sessions/${id}/messages`);
      const body = await res.json();
      this.messages = body.messages || [];
    },
    async deleteSession(id) {
      const ok = await window.pqlConfirm(
        'Delete session?',
        'This permanently deletes the session and its messages.',
        { confirmLabel: 'Delete' }
      );
      if (!ok) return;
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
