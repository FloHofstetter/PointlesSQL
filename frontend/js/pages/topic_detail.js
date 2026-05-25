// Auto-extracted from frontend/templates/pages/topic_detail.html.
// Exports: topicDetail.
//
export function topicDetail(topic) {
  return {
    topic: topic,
    loaded: false,
    detail: {},
    dps: [],
    viewerFollows: false,
    async init() {
      await this.load();
    },
    async load() {
      try {
        const res = await fetch('/api/topics/' + this.topic.slug);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.detail = { followers: data.followers };
        this.dps = data.data_products || [];
        this.viewerFollows = !!data.viewer_follows;
      } catch (e) {
        console.error('topic load failed', e);
      } finally {
        this.loaded = true;
      }
    },
    async follow() {
      try {
        const res = await fetch('/api/topics/' + this.topic.slug + '/follow', { method: 'POST' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.viewerFollows = true;
        await this.load();
      } catch (e) {
        console.error('follow failed', e);
      }
    },
    async unfollow() {
      try {
        const res = await fetch('/api/topics/' + this.topic.slug + '/follow', { method: 'DELETE' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.viewerFollows = false;
        await this.load();
      } catch (e) {
        console.error('unfollow failed', e);
      }
    },
  };
}
