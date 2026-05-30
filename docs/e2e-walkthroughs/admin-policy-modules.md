# Admin policy-modules walkthrough

> **Mode:** `browser` · **Surface:** /admin/policy-modules

End-to-end exercise of the Cedar policy-modules admin surface: list
view, create dialog, dry-run dialog, delete confirmation.  Pins the
Alpine x-data factory + Bootstrap modal interplay (the modal pattern
that surprised W2 — see [[feedback_bootstrap_modal_x_show]]).

## Preconditions

- E2E stack up + `auth.md` ran first (admin signed in).
- Playwright MCP Firefox (bundled, not system Chrome).

## Walkthrough

1. **Land on the policy-modules page.**
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/policy-modules')`.
   - Assert: page title contains "Policy modules · PointlesSQL".
     Heading reads "Policy modules".  The empty-state row reads "No
     policy modules yet." when the workspace is fresh.

2. **Open the New-module dialog.**
   - Action: click the "New module" button (top-right).
   - Assert: a modal with title "New policy module" appears, with a
     Name input, Cedar source textarea, and an Enabled toggle.

3. **Create a permit-all module.**
   - Action: fill Name = `walkthrough_permit`, Cedar source =
     `permit(principal, action == Action::"read", resource);`.
   - Action: click Create.
   - Assert: the modal closes and the table now shows one row with
     name `walkthrough_permit`, version `v1`, an "on" badge, and
     four action buttons (Edit / Test / Log / Delete).

4. **Dry-run the module.**
   - Action: click the row's "Test" button.
   - Assert: the dry-run modal opens with three monospace inputs:
     Principal = `User::"test"`, Action = `Action::"read"`,
     Resource = `DataProduct::"main.silver"`.
   - Action: click "Evaluate".
   - Assert: a green `permit` alert appears.

5. **Open the decision log.**
   - Action: close the test modal; click the row's "Log" button.
   - Assert: the decision log modal opens.  The table shows at least
     one row from the dry-run with `effect = permit`.

6. **Delete the module.**
   - Action: close any open modal; click the row's "Delete" button;
     accept the confirm.
   - Assert: the row disappears; empty-state row reappears.

## Found bugs

(none at time of writing — fill in during the first live replay)
