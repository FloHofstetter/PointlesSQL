// Auto-extracted from frontend/templates/pages/agent_profile.html.
// Exports: agentProfile.
//
export function agentProfile(agent) {
  return {
    agent: agent,
    loaded: false,
    profile: { display_name: agent.display_name, avatar_kind: agent.avatar_kind, principal: {} },
    recentComments: [],
    runStats: {},
    async init() {
      await this.load();
    },
    async load() {
      try {
        const res = await fetch('/api/agents/' + this.agent.slug + '/profile');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.profile = data.agent || this.profile;
        this.recentComments = data.recent_comments || [];
        this.runStats = data.run_stats || {};
      } catch (e) {
        console.error('agent profile load failed', e);
      } finally {
        this.loaded = true;
      }
    },
  };
}
