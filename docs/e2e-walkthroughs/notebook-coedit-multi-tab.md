# Notebook co-edit — multi-tab replay

> **Mode:** `browser` · **Surface:** `/notebooks/edit/{path}` + `/ws/notebook/coedit/{uuid}`

Exercises the real-time co-edit pipeline against a live
stack with two browser tabs sharing the same notebook.  Verifies
that text typed in tab A appears in tab B sub-second, that the
peer-avatar rail paints the other tab's user, and that closing
one tab drops the peer from the survivor's rail.  Also smokes the
Phase-105.5 save-barrier and Phase-105.6 agent-presence REST
endpoint as opportunistic add-ons.

Replay strategy: open a second tab via the Playwright-MCP
`browser_tabs` tool family; both tabs share cookies inside the
same browser context, so a single auth from [`auth.md`](auth.md)
covers both.  If you replay only this playbook, run the auth
steps once and continue here.

## Preconditions

- Stack up — `docker compose -f docker/docker-compose.yml -f
  docker/docker-compose.e2e.yml up -d`.
- A user account exists with **edit** rights on at least one
  notebook (replay [`auth.md`](auth.md) for the default admin).
- An empty notebook file at
  `notebooks/coedit-multi-tab.py` reachable from the workspace
  browser at `http://127.0.0.1:8000/notebooks/edit/coedit-multi-tab.py`.
  Create it from the notebook workspace UI if absent — replay
  [`notebook-overview.md`](notebook-overview.md) for the
  create-and-open flow.

## Walkthrough

1. **Tab 1: open the notebook editor.**
   - Action: `browser_navigate(url='http://127.0.0.1:8000/notebooks/edit/coedit-multi-tab.py')`.
   - Assert: the `[data-testid="notebook-coedit-dot"]` element
     paints; its class settles on **`bg-success`** within 3 s
     (initial sync_step2 completed against the Sprint-105.2 hub.5 collapsed the verbose toolbar pill into a single
     colour-coded dot whose tooltip preserves the old "Live" label).
   - Assert: the importmap script in the page source contains
     `"yjs":`, `"y-protocols/awareness":`, and
     `"y-codemirror.next":` entries.

2. **Tab 2: open the same notebook in a sibling tab.**
   - Action: `browser_tabs(action='new')`.
   - Action: in the new tab,
     `browser_navigate(url='http://127.0.0.1:8000/notebooks/edit/coedit-multi-tab.py')`.
   - Assert: the same live pill paints on tab 2.

3. **Peer rails populate on both sides.**
   - Tab 1 → Tab 2 visibility: in tab 1,
     `[data-testid="notebook-coedit-peers"]` is non-empty within
     2 s, and at least one
     `[data-testid^="notebook-coedit-peer-"]` avatar paints with
     the same user id as the currently-signed-in user (since
     both tabs share the same cookie, both peer rails see the
     other tab as the same user — two clientIds, one id).
   - Tab 2: identical expectation, mirrored.

4. **Type in tab 1 → tab 2 receives.**
   - Action (tab 1): click the first cell's CodeMirror surface
     (`.cm-content`), type `co_edit_marker = 'hello-from-tab-1'`.
   - Assert (tab 2): within 2 s, the first cell's `.cm-content`
     contains the literal `hello-from-tab-1`.

5. **Type in tab 2 → tab 1 receives.**
   - Action (tab 2): focus the first cell's `.cm-content`, append
     `\nreplied = 'hello-from-tab-2'`.
   - Assert (tab 1): within 2 s, the first cell carries both the
     tab-1 line *and* the tab-2 append.

6. **Save in tab 1 → no editor reset in tab 2.**
   - Action (tab 1): press `Cmd/Ctrl + S` (or click the
     toolbar's Save button).
   - Assert (tab 1): the "Saved" badge replaces "Unsaved"
     within 2 s; the cell content stays intact.
   - Assert (tab 2): no editor reset; the cell content stays
     identical to the pre-save state.  the save-barrier ensures any reconciled cell_uuid changes
     reach tab 2 via a `tag=0x04` advisory before it can
     desync.

7. **Optional: agent presence smoke.**
   - Action (any tab): from a CLI with admin auth (or via
     `browser_evaluate` calling `fetch`),
     POST to
     `/api/notebooks/{notebook_uuid}/coedit/agent-presence`
     with body
     `{"agent_run_id": "run-replay", "name": "hermes",
       "cell_uuid": "<any uuid>", "action": "editing"}`.
   - Assert: response `{"status": "broadcast"}` (a hub is
     open because both tabs are connected).
   - Assert (tab 1 + tab 2): a new pseudo-peer avatar with the
     robot icon appears in the peer rail.
   - Cleanup: POST the same body with `"action": "clear"`.
     The robot avatar disappears within a frame on both tabs.

8. **Close tab 2 → peer drops from tab 1's rail.**
   - Action: `browser_tabs(action='close', index=<tab-2 index>)`.
   - Assert (tab 1): within 5 s the
     `[data-testid^="notebook-coedit-peer-"]` for the closing
     tab disappears from the rail.  The Sprint-105.4
     `window.beforeunload` handler clears the local awareness
     state synchronously; the WS close triggers the hub's
     teardown path for the last-subscriber-leaves case if
     applicable.

## Playwright MCP script

```text
browser_navigate('http://127.0.0.1:8000/notebooks/edit/coedit-multi-tab.py')
browser_wait_for(text='Live')           # coedit pill state
browser_snapshot()

browser_tabs(action='new')
browser_navigate('http://127.0.0.1:8000/notebooks/edit/coedit-multi-tab.py')
browser_wait_for(text='Live')

# Tab 2 → Tab 1 hand-off — focus a cell + type
browser_click(element='first cell CodeMirror surface')
browser_type(element='first cell CodeMirror', text="co_edit_marker = 'hello-from-tab-1'")

browser_tabs(action='select', index=0)  # switch to tab 1
browser_wait_for(text='hello-from-tab-1')

# Tab 1 → Tab 2
browser_click(element='first cell CodeMirror surface')
browser_type(element='first cell CodeMirror', text="\nreplied = 'hello-from-tab-2'")

browser_tabs(action='select', index=1)
browser_wait_for(text='hello-from-tab-2')

# Save in tab 1
browser_tabs(action='select', index=0)
browser_press_key(key='Meta+s')  # or Ctrl+s on linux
browser_wait_for(text='Saved')

# Agent presence smoke
browser_evaluate(function='''() => fetch(
  `/api/notebooks/${document.querySelector("[data-testid=notebook-coedit-dot]")
       .closest("[x-data]")
       ?.__x?.$data?.notebookUuid}/coedit/agent-presence`,
  {method: "POST", headers: {"Content-Type":"application/json"},
   body: JSON.stringify({agent_run_id:"run-replay", name:"hermes",
                         cell_uuid:null, action:"editing"})}
).then(r => r.json())''')
browser_snapshot()  # peer rail contains the robot avatar

browser_tabs(action='close', index=1)
browser_tabs(action='select', index=0)
browser_wait_for(textGone='hello-from-tab-2-peer-clientId')  # ad-hoc assertion
```

## Selector reference

| Selector | Source |
| --- | --- |
| `[data-testid="notebook-coedit-dot"]` | toolbar co-edit status dot (Sprint 112.5; replaces the verbose `notebook-coedit-pill`) |
| `[data-testid="notebook-coedit-peers"]` | peer-avatar rail container |
| `[data-testid^="notebook-coedit-peer-"]` | per-peer avatar disc |
| `#pql-cell-host-{cell.id}` | per-cell editor host |
| `.cm-content` | CodeMirror editable surface |

## Found bugs

_Track surfaced issues here on replay.  Each entry should
include a one-line summary + the file:line of the fix._
