# Notebook walkthrough

Verifies the embedded-JupyterLab surface in both enabled and disabled
states. Two passes against the same stack — the second pass flips
`POINTLESSQL_JUPYTER_ENABLED=false` on the host env to exercise the
short-circuit path.

## Preconditions

- Stack up with the e2e overlay; `admin@pql.test` logged in.
- Pass 1 assumes the default (`POINTLESSQL_JUPYTER_ENABLED=true`
  from the overlay) and a fully-started JupyterLab subprocess
  (30 s startup grace per `jupyter.py:86`).
- **Not in scope**: driving JupyterLab cells from inside the
  iframe. Playwright's frame reach is restricted and cell-level
  interaction needs a child-frame context that Phase 7 explicitly
  excluded. This playbook only proves the harness is wired.

## Walkthrough

### Pass 1 — Jupyter enabled (default)

1. **Navbar tab and route**.
   - Action: `browser_navigate('http://127.0.0.1:8000/notebook')`
   - Assert: page title contains "Notebook", navbar shows the
     "Notebook" link with `active` class, no console errors.

2. **Status endpoint reports enabled + running**.
   - Action:
     ```js
     await fetch('/api/jupyter/status').then(r => r.json())
     ```
   - Assert (may take up to 30 s on first start — the subprocess
     polls `http://localhost:8888/lab` every 500 ms):
     `{enabled: true, running: true, port: 8888}`.

3. **Loader Alpine component transitions to the iframe**.
   - Action:
     ```js
     const d = Alpine.$data(document.querySelector('[x-data*="jupyterLoader"]'));
     return { ready: d.ready, failed: d.failed, attempts: d.attempts };
     ```
   - Assert: `ready === true` (once the loader's polling sees the
     subprocess up), `failed === false`.

4. **Iframe src**.
   - Action:
     ```js
     document.querySelector('iframe')?.src
     ```
   - Assert: equals `http://localhost:8888/lab` (hard-coded per
     `pages/notebook.html`).

5. **Iframe renders JupyterLab**.
   - Action: `browser_wait_for(time=5)` (give the iframe document
     a chance to boot).
   - Assert: via
     `browser_evaluate(() => document.querySelector('iframe').contentDocument.title)`
     — if the browser allows cross-frame access, the title
     contains "JupyterLab". If blocked by same-origin rules,
     document this limitation in the Found-bugs section as a
     harness note (not a bug).

### Pass 2 — Jupyter disabled

6. **Restart the stack with `POINTLESSQL_JUPYTER_ENABLED=false`**.
   - Action (shell, not browser):
     ```bash
     POINTLESSQL_JUPYTER_ENABLED=false docker compose \
         -f docker-compose.yml -f docker-compose.e2e.yml \
         up -d --force-recreate pointlessql
     ```
   - Wait for `docker compose ps` to show `(healthy)`.

7. **Log back in** (Alembic data survived, so the auth.md users
   are still valid).

8. **Status endpoint reports disabled**.
   - Action: `fetch('/api/jupyter/status').then(r => r.json())`
   - Assert: `{enabled: false, running: false, port: 8888}`.

9. **Navbar tab is still present**.
   - Assert: the "Notebook" link is still in the navbar
     (`base.html:34` renders it unconditionally). This is an
     intentional trade-off — the disabled state is communicated
     on the target page, not via nav-link visibility.

10. **Route renders disabled state**.
    - Action: `browser_navigate('http://127.0.0.1:8000/notebook')`
    - Assert: the loader Alpine short-circuits: `d.failed` is
      `true` (polling exhausts because `running` never flips),
      or the page renders a "Notebook Disabled" fallback message
      depending on template logic. Either way, no iframe loads.

11. **Restore the default** (flip the env back) so downstream
    playbooks start from a clean state:
    ```bash
    POINTLESSQL_JUPYTER_ENABLED=true docker compose \
        -f docker-compose.yml -f docker-compose.e2e.yml \
        up -d --force-recreate pointlessql
    ```

## Playwright MCP script

```text
# Pass 1
browser_navigate('http://127.0.0.1:8000/notebook')
browser_evaluate('async () => await fetch("/api/jupyter/status").then(r => r.json())')
browser_evaluate('() => { const d = Alpine.$data(document.querySelector("[x-data*=\\"jupyterLoader\\"]")); return {ready: d.ready, failed: d.failed}; }')
browser_evaluate('() => document.querySelector("iframe")?.src')

# (shell — not an MCP tool)
# POINTLESSQL_JUPYTER_ENABLED=false docker compose ... up -d --force-recreate pointlessql

# Pass 2 — re-login then re-navigate
browser_navigate('http://127.0.0.1:8000/auth/login')
browser_fill_form(...)
browser_click(element='Sign in')
browser_navigate('http://127.0.0.1:8000/notebook')
browser_evaluate('async () => await fetch("/api/jupyter/status").then(r => r.json())')
```

## Found bugs

_No bugs surfaced. Live run:_

- _Pass 1: `/api/jupyter/status` returned `{enabled:true,
  running:true, port:8888}` within 30 s of startup; Alpine
  `jupyterLoader().ready` flipped to true; iframe `src` was
  `http://localhost:8888/lab`._
- _Pass 2 with `POINTLESSQL_JUPYTER_ENABLED=false`: the template
  short-circuits the `jupyterLoader()` component and renders the
  "Notebook Disabled" card with the hint "Set
  POINTLESSQL_JUPYTER_ENABLED=true to enable the embedded
  notebook." — no iframe, no loader polling, no console errors._
