# Model serving walkthrough

> **Mode:** `browser` · **Surface:** /serving + /api/serving-endpoints

End-to-end exercise of the model-serving cockpit: create an endpoint
for a registry model, start it (watching the 2-second poll paint the
`starting` badge), score a request through the "Try it" drawer,
stop, and delete. Lifecycle mutations need the optional `mlflow`
extra (`pip install pointlessql[ml]`); without it Start answers 503
while the list and create stay usable.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in) — though any signed-in user can drive this page; no
  admin gate.
- A registered model exists in the ML registry with at least one
  version (the [`agent-ml-registry.md`](agent-ml-registry.md)
  walkthrough leaves one behind; any sklearn pyfunc model works).
- Playwright MCP Firefox (`--browser firefox`); see
  [admin-console.md](admin-console.md) for the stale-profile-lock
  recovery note.

## Walkthrough

### Part A — Create (3 steps)

1. **Land on the cockpit**.
   - Action: `browser_navigate('http://127.0.0.1:8000/serving')`.
   - Assert: title `Model Serving · PointlesSQL`, heading "Model
     Serving" with the rocket icon, breadcrumb Home → Model
     Serving, counter reads "0 endpoints" on a fresh stack, and the
     empty-state row "No serving endpoints yet." shows.

2. **Create an endpoint**.
   - Action: fill Name = `e2e-scorer`, Model name = the registry
     model's name, Model version = `1` (the help text under the
     version field reads "@alias or number"); click "Create".
   - Assert: the table grows a row `e2e-scorer` with the model
     shown as `name / 1`, state badge `stopped` (grey), 0
     invocations, last invoked `—`.

3. **Reject a malformed name**.
   - Action: fill Name = `has space`, any model/version, click
     "Create".
   - Assert: the red alert under the form shows the
     `1-128 chars from [A-Za-z0-9_-]` validation message; no row
     is added.

### Part B — Lifecycle (3 steps)

4. **Start the endpoint**.
   - Action: click "Start" on the `e2e-scorer` row.
   - Assert: the badge flips to `starting` (yellow) within ~2
     seconds — the page re-fetches the list every 2 s while any
     endpoint is starting (60 s cap) — then settles on `ready`
     (green) once the scoring worker passes health. The Start
     button is disabled while `starting`/`ready`.
   - Note: without the `mlflow` extra the POST answers 503 and the
     red alert shows the "optional mlflow extra" message; the badge
     stays `stopped`. That is the expected degraded mode.

5. **Failure surfaces in the badge tooltip**.
   - Action: (only on a stack where a bad model reference is easy
     to mint) create `e2e-broken` pointing at a nonexistent model
     version and click "Start".
   - Assert: badge flips to `failed` (red); hovering it shows the
     stderr tail in the `title` tooltip (`last_error`).

6. **Stop**.
   - Action: click "Stop" on the `e2e-scorer` row.
   - Assert: badge returns to `stopped`; "Try it" disappears
     (it only renders for `ready` endpoints).

### Part C — Scoring (2 steps)

7. **Send a request through the Try-it drawer**.
   - Action: start `e2e-scorer` again, wait for `ready`, click
     "Try it". The drawer opens with a JSON textarea prefilled
     with `{"dataframe_records": [{}]}`. Replace the empty record
     with the model's feature columns, click "Send".
   - Assert: the worker's raw JSON answer renders in the `<pre>`
     below (e.g. `{"predictions": [...]}`); the row's invocation
     count increments and "last invoked" flips to "just now".

8. **Malformed JSON fails client-side**.
   - Action: break the textarea JSON (drop a brace), click "Send".
   - Assert: the `<pre>` shows "Request body is not valid JSON:
     …" — no network request fires
     (`browser_network_requests` shows no new POST).

### Part D — Cleanup (1 step)

9. **Delete the endpoint**.
   - Action: click "Delete" on each test row, accept the confirm
     dialog.
   - Assert: rows disappear; the empty state returns. Console
     stays free of errors for the whole walkthrough.

## Cleanup

```bash
# In case a row survived the UI pass:
curl -sS -X DELETE http://127.0.0.1:8000/api/serving-endpoints/e2e-scorer -b cookies.txt
curl -sS -X DELETE http://127.0.0.1:8000/api/serving-endpoints/e2e-broken -b cookies.txt
```
