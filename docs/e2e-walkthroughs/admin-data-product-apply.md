# Admin data-product-apply walkthrough

> **Mode:** `browser` · **Surface:** /admin/data-product-apply

End-to-end exercise of the Data-Product-as-Code surface: paste a
YAML spec, run Plan to see the diff, run Apply to commit, verify
re-running yields an empty plan (idempotency invariant).

## Preconditions

- E2E stack up + `auth.md` ran first (admin signed in).
- A `main` catalog exists (the seed-e2e script provides one).

## Walkthrough

1. **Land on the data-product-apply page.**
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/data-product-apply')`.
   - Assert: page title contains "Data-product apply · PointlesSQL".
     Two cards labelled "Spec (YAML / JSON)" and "Plan / Outcome".
     The right-hand card shows the placeholder text "Plan + outcome
     render here.".

2. **Paste a minimal spec.**
   - Action: focus the textarea and type:
     ```yaml
     name: walkthrough_dp
     catalog: main
     schema: walkthrough_apply
     domain: ""
     owner_email: admin@pql.test
     output_ports: []
     ```
   - Assert: the Plan + Apply buttons become enabled.

3. **Run Plan.**
   - Action: click Plan.
   - Assert: the right-hand card shows three badges (additions /
     modifications / removals) with a non-zero "add" count, and a
     monospace JSON viewer renders the plan dict.

4. **Run Apply.**
   - Action: click Apply.
   - Assert: the badges update (additions move into the applied set),
     an "Outcome" block appears with `ops_applied > 0`.

5. **Idempotency: re-run Plan.**
   - Action: click Plan again without editing the spec.
   - Assert: the additions badge reads `0 add`, modifications and
     removals are also `0` — the spec is fully reconciled.

6. **Error path: malformed YAML.**
   - Action: edit the textarea to insert a stray colon (e.g. `name:
     bad: shape`); click Plan.
   - Assert: the alert-danger row appears with text starting "Plan
     failed" or "invalid spec".

## Found bugs

(none at time of writing — fill in during the first live replay)
