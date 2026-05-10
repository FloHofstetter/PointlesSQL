# Lens MCP server walkthrough

> **Mode:** `hermes` · **Phase:** 65 · **Surface:** `pointlessql lens-mcp` (stdio) + `/mcp/health` + `/mcp/info`

End-to-end exercise of the Lens MCP server (Phase 65.4): mint an
analyst-scoped api-key, spawn the `lens-mcp` subprocess, send a raw
MCP `initialize` + `tools/list` + `tools/call` round-trip via stdio,
and verify the audit row landed.  Validates the IDE-consumer path
(Claude Desktop, Cursor, Hermes-as-MCP-client) without spinning up
the browser.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first.

## Walkthrough

### Part A — Provision an analyst api-key (3 steps)

1. **Mint a fresh analyst-scoped key**.
   - Action: log in as admin, then:
     ```bash
     curl -X POST http://127.0.0.1:8000/api/admin/api-keys \
       -H 'Content-Type: application/json' -b cookies.txt \
       -d '{"name":"lens-mcp-walkthrough","analyst":true}'
     ```
   - Assert: response carries `secret:"<plaintext>"` (shown
     once); `name:"lens-mcp-walkthrough"`, `analyst:true`.
   - Save the secret as `LENS_KEY` in your shell:
     ```bash
     export LENS_KEY="$(jq -r .secret <<<'<paste-response>')"
     ```

2. **Verify the key resolves via /mcp/info**.
   - Action: `curl -H "Authorization: Bearer $LENS_KEY" http://127.0.0.1:8000/mcp/info`
   - Assert: `200 OK`, body shape:
     ```json
     {"workspace_id": 1, "key_name": "lens-mcp-walkthrough", "scopes": ["analyst"]}
     ```

3. **Hit the health route (no auth)**.
   - Action: `curl http://127.0.0.1:8000/mcp/health`
   - Assert: `{"status": "ok", "tools": <int>}` with `tools >= 7`.

### Part B — Spawn the stdio MCP server + drive a tool call (5 steps)

4. **Start the lens-mcp subprocess**.
   - Action:
     ```bash
     LENS_API_KEY="$LENS_KEY" \
       POINTLESSQL_DB_URL=sqlite:///./pointlessql.db \
       uv run pointlessql lens-mcp
     ```
     The process blocks on stdin; pipe the JSON-RPC frames through
     it from another shell (or use a here-doc).

5. **Send the MCP initialize handshake**.
   - Wire format: one JSON-RPC frame per line (newline-delimited).
     ```bash
     printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"lens-walkthrough","version":"0.1"}}}' \
       | LENS_API_KEY="$LENS_KEY" uv run pointlessql lens-mcp
     ```
   - Assert: server emits a JSON line carrying
     `result.serverInfo.name="PointlesSQL Lens"` and a non-empty
     `result.capabilities` dict.

6. **List the tools**.
   - Action: append a `tools/list` frame to the same pipe.
     ```bash
     printf '%s\n%s\n' \
       '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \
       '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
       | LENS_API_KEY="$LENS_KEY" uv run pointlessql lens-mcp
     ```
   - Assert: response carries a `result.tools` array of length
     ≥ 7; tool names include `provenance`, `query`, `list_catalogs`.

7. **Call the `provenance` tool**.
   - Action: append a `tools/call` frame:
     ```bash
     printf '%s\n%s\n%s\n' \
       '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' \
       '{"jsonrpc":"2.0","id":2,"method":"tools/list",...}' \
       '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"provenance","arguments":{"table_fqn":"main.silver.t"}}}' \
       | ...
     ```
   - Assert: response carries a `result.content` array; the first
     content entry is text describing the table-scope mode.

8. **Verify the audit-trail row landed**.
   - Action: log back in as admin, run
     ```bash
     curl -b cookies.txt http://127.0.0.1:8000/api/audit/history?limit=10
     ```
   - Assert: at least one row referencing `lens-mcp-walkthrough` as
     the principal (Bearer-key callers carry their key name as
     attribution).

## Coverage

* `pointlessql lens-mcp` CLI bootstraps a stdio MCP server.
* `/mcp/health` + `/mcp/info` introspection routes.
* JSON-RPC handshake + `tools/list` + `tools/call` over stdio.
* Audit-trail propagation for MCP-driven tool calls.
