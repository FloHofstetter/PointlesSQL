// Alpine factory for the Agent page (pages/agent_hermes.html).
// Exports: agentHermes.
//
// Reads the managed-instance status and drives the Restart control.
// The embedded dashboard itself lives in the same-origin /hermes
// reverse-proxy iframe; this component only owns the status chip and
// the start/stop lifecycle buttons.

export function agentHermes() {
  return {
    loaded: false,
    busy: false,
    status: {
      enabled: false,
      mode: null,
      managed: false,
      running: false,
      healthy: false,
    },

    async init() {
      await this.loadStatus();
    },

    get statusLabel() {
      if (!this.loaded) return 'Checking…';
      if (!this.status.enabled) return 'Disabled';
      if (this.status.healthy) return 'Running';
      if (this.status.running) return 'Starting…';
      return 'Stopped';
    },

    get statusClass() {
      if (!this.loaded) return 'text-bg-secondary';
      if (this.status.healthy) return 'text-bg-success';
      if (!this.status.enabled) return 'text-bg-secondary';
      return 'text-bg-warning';
    },

    async loadStatus() {
      try {
        const res = await fetch('/api/hermes/status');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.status = await res.json();
      } catch (e) {
        console.error('hermes status load failed', e);
      } finally {
        this.loaded = true;
      }
    },

    async restart() {
      if (this.busy) return;
      this.busy = true;
      try {
        // Stop then start gives a clean bounce; both are no-ops in
        // external mode, so Restart just re-probes there.
        await fetch('/api/hermes/stop', { method: 'POST' });
        const res = await fetch('/api/hermes/start', { method: 'POST' });
        if (res.ok) {
          this.status = await res.json();
        } else {
          await this.loadStatus();
        }
      } catch (e) {
        console.error('hermes restart failed', e);
        await this.loadStatus();
      } finally {
        this.busy = false;
      }
    },
  };
}
