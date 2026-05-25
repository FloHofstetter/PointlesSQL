// Auto-extracted from frontend/templates/pages/me_settings.html.
// Exports: meSettingsForm.
//
export function meSettingsForm(initial) {
  return {
    settings: initial,
    status: '',
    statusOk: true,
    init() {
      /* no async load — server already injected ``settings`` */
    },

    async toggle(checked) {
      this.status = '';
      try {
        const res = await fetch('/api/me/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ digest_email_optin: checked }),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.settings = await res.json();
        this.status = 'Saved.';
        this.statusOk = true;
      } catch (e) {
        this.status = 'Save failed.';
        this.statusOk = false;
      }
    },
  };
}
