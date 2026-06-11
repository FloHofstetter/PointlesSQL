# Notebook debugger walkthrough

> **Mode:** `browser` · **Surface:** notebook editor (debug panel)

Exercise step-through debugging of a notebook cell: set a
breakpoint, hit it, inspect frames and variables, step, and
continue.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first.
- A notebook with a code cell like:
  ```python
  total = 0
  for i in range(5):
      total += i
  print(total)
  ```
- Kernel started (run any cell once).

## Walkthrough

### Part A — break + inspect (3 steps)

1. **Arm a breakpoint**.
   - Action: open the debug affordance for the cell (gutter click
     or the panel's line input — whichever the build ships) at the
     `total += i` line; start **Debug cell**.
   - Assert: the debug panel shows a "Paused" badge naming the
     stopped frame.

2. **Inspect state**.
   - Action: read the panel's stack + variables.
   - Assert: the top frame points at the cell source; variables
     list `i` and `total` with plausible values (first stop:
     `i = 0`, `total = 0`).

3. **Step**.
   - Action: click **Next** twice.
   - Assert: variable values advance (`total` grows) — the panel
     refreshes per stop.

### Part B — finish (2 steps)

4. **Continue**.
   - Action: **Continue** until no breakpoints remain.
   - Assert: the pause badge clears; the cell completes and its
     output (`10`) renders as usual.

5. **Stop mid-debug**: re-enter the debugger, click **Stop**.
   - Assert: debug state clears without wedging the kernel — a
     plain re-run of the cell still works.
