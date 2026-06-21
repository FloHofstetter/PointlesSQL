// Hosted-apps list (/apps).
//
// hostedApps: create form + per-app lifecycle (start / stop /
// delete). The table is seeded server-side with the same shape
// GET /api/apps answers, so refresh fetches can swap rows in
// without reshaping. Start blocks server-side until the worker is
// healthy; the refresh afterwards repaints the state badge + port.

const FASTAPI_EXAMPLE = [
  'from fastapi import FastAPI',
  '',
  'app = FastAPI()',
  '',
  '',
  '@app.get("/")',
  'def home() -> dict[str, str]:',
  '    return {"hello": "from a hosted app"}',
  '',
].join('\n');

export function hostedApps(initial, canAdmin) {
  return {
    apps: initial || [],
    canAdmin: !!canAdmin,
    form: {
      title: '',
      kind: 'fastapi',
      command_override: '',
      source_code: FASTAPI_EXAMPLE,
      env_text: '',
    },
    creating: false,
    createError: '',
    error: '',
    busy: {},
    genie: {
      kind: 'fastapi',
      title: '',
      prompt: '',
      building: false,
      error: '',
      notice: '',
    },

    ago(iso) {
      if (!iso) return '—';
      if (typeof window.pqlRelativeTime === 'function') return window.pqlRelativeTime(iso);
      return iso;
    },

    stateBadge(state) {
      return (
        {
          stopped: 'bg-secondary',
          starting: 'bg-warning text-dark',
          ready: 'bg-success',
          failed: 'bg-danger',
        }[state] || 'bg-secondary'
      );
    },

    async refresh() {
      const res = await window.pqlApi.fetch('/api/apps', { silent: true });
      if (res.ok) this.apps = (res.data && res.data.apps) || [];
    },

    async create() {
      this.createError = '';
      const title = this.form.title.trim();
      if (!title) {
        this.createError = 'Title is required.';
        return;
      }
      const payload = {
        title: title,
        kind: this.form.kind,
        source_code: this.form.source_code,
      };
      if (this.form.kind === 'command') {
        payload.command_override = this.form.command_override;
      }
      const envText = this.form.env_text.trim();
      if (envText) {
        let env;
        try {
          env = JSON.parse(envText);
        } catch (err) {
          this.createError = 'Env is not valid JSON: ' + err.message;
          return;
        }
        payload.env = env;
      }
      this.creating = true;
      const res = await window.pqlApi.fetch('/api/apps', { method: 'POST', body: payload });
      this.creating = false;
      if (!res.ok) {
        this.createError = res.error || 'Failed to create app';
        return;
      }
      this.form = {
        title: '',
        kind: 'fastapi',
        command_override: '',
        source_code: FASTAPI_EXAMPLE,
        env_text: '',
      };
      await this.refresh();
    },

    async genieBuild() {
      this.genie.error = '';
      this.genie.notice = '';
      const prompt = this.genie.prompt.trim();
      if (!prompt) {
        this.genie.error = 'Describe the app first.';
        return;
      }
      const payload = { prompt: prompt, kind: this.genie.kind };
      const title = this.genie.title.trim();
      if (title) payload.title = title;
      this.genie.building = true;
      const res = await window.pqlApi.fetch('/api/apps/genie-build', {
        method: 'POST',
        body: payload,
      });
      this.genie.building = false;
      if (!res.ok) {
        this.genie.error = res.error || 'Failed to build app';
        return;
      }
      const made = res.data && res.data.app;
      const viaLlm = !!(res.data && res.data.used_llm);
      this.genie.prompt = '';
      this.genie.title = '';
      this.genie.notice = made
        ? 'Created "' +
          made.title +
          '"' +
          (viaLlm ? ' with the configured LLM.' : ' as a scaffold (no LLM configured).')
        : 'App created.';
      await this.refresh();
    },

    async start(app) {
      this.error = '';
      this.busy[app.slug] = true;
      const res = await window.pqlApi.fetch(
        '/api/apps/' + encodeURIComponent(app.slug) + '/start',
        { method: 'POST' }
      );
      this.busy[app.slug] = false;
      if (!res.ok) this.error = res.error || 'Failed to start app';
      await this.refresh();
    },

    async stop(app) {
      this.error = '';
      this.busy[app.slug] = true;
      const res = await window.pqlApi.fetch('/api/apps/' + encodeURIComponent(app.slug) + '/stop', {
        method: 'POST',
      });
      this.busy[app.slug] = false;
      if (!res.ok) this.error = res.error || 'Failed to stop app';
      await this.refresh();
    },

    async remove(app) {
      if (!window.confirm('Delete app "' + app.title + '"?')) return;
      this.busy[app.slug] = true;
      const res = await window.pqlApi.fetch('/api/apps/' + encodeURIComponent(app.slug), {
        method: 'DELETE',
      });
      this.busy[app.slug] = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to delete app';
        return;
      }
      await this.refresh();
    },
  };
}
