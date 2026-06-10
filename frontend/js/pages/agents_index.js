// Agents directory page factory.
export function agentsIndex(ctx) {
  return {
    isAdmin: !!ctx.is_admin,
    loaded: false,
    agents: [],
    async init() {
      await this.load();
    },
    async load() {
      try {
        const res = await fetch('/api/agents');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        this.agents = (await res.json()).agents || [];
      } catch (e) {
        console.error('agents load failed', e);
      } finally {
        this.loaded = true;
      }
    },
  };
}
