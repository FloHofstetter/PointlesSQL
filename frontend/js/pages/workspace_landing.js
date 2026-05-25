// Auto-extracted from frontend/templates/pages/workspace_landing.html.
// Exports: workspaceLanding.
//
export function workspaceLanding(slug) {
  return {
    slug: slug,
    pins: [],
    pinsLoaded: false,
    activity: [],
    activityLoaded: false,
    showAddPin: false,
    newPinTargetId: '',
    async init() {
      await Promise.all([this.refreshPins(), this.refreshActivity()]);
    },
    async refreshPins() {
      this.pinsLoaded = false;
      const res = await window.pqlApi.fetch('/api/workspaces/' + slug + '/pins');
      this.pins = (res && res.ok && res.data && res.data.pins) || [];
      this.pinsLoaded = true;
    },
    async refreshActivity() {
      this.activityLoaded = false;
      const res = await window.pqlApi.fetch('/api/workspaces/' + slug + '/activity');
      this.activity = (res && res.ok && res.data && res.data.activity) || [];
      this.activityLoaded = true;
    },
    async addPin() {
      const targetId = parseInt(this.newPinTargetId, 10);
      if (!targetId) return;
      const res = await window.pqlApi.fetch('/api/workspaces/' + slug + '/pins', {
        method: 'POST',
        body: JSON.stringify({social_target_id: targetId}),
      });
      if (res && res.ok) {
        this.showAddPin = false;
        this.newPinTargetId = '';
        await this.refreshPins();
      }
    },
    async removePin(targetId) {
      await window.pqlApi.fetch('/api/workspaces/' + slug + '/pins/' + targetId, {
        method: 'DELETE',
      });
      await this.refreshPins();
    },
  };
}
