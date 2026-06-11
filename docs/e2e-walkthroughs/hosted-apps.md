# Hosted apps walkthrough

> **Mode:** `browser` · **Surface:** /apps + /apps/{slug}

Exercise app hosting end to end: create a FastAPI app from inline
source, start it, reach it through the authenticated proxy, read
its logs, and stop it.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first (admin —
  app management is admin-gated).

## Walkthrough

### Part A — create + start (3 steps)

1. **Land on the list**.
   - Action: `browser_navigate('http://127.0.0.1:8000/apps')`.
   - Assert: heading "Apps", empty state, "New app" for the admin.

2. **Create a FastAPI app**.
   - Action: title `E2E Hello`, kind `fastapi`, source:
     ```python
     from fastapi import FastAPI

     app = FastAPI()

     @app.get("/")
     def hello():
         return {"hello": "lakehouse"}
     ```
   - Assert: detail page shows state `stopped`.

3. **Start it**.
   - Action: click **Start**; wait for the health poll.
   - Assert: state flips `starting` → `ready` with a port; the
     iframe (or opening `/apps/<slug>/proxy/` directly) renders
     `{"hello":"lakehouse"}`.

### Part B — guards + lifecycle (3 steps)

4. **Auth is enforced**: an anonymous request to
   `/apps/<slug>/proxy/` redirects to login / 401 — the worker
   itself listens only on loopback.

5. **Logs**: the detail page's log panel tails the worker's
   stderr (uvicorn startup lines visible).

6. **Stop**: click **Stop** → state `stopped`; the proxy now
   answers 503 with the state in the detail.
