# Computational Governance — policy, classifications, forget, scan

> **Mode:** `hybrid` · **Surface:** product Governance tab (policy / classifications / right-to-be-forgotten) + `/admin/governance` workspace default + compliance scan

Governance is policy-as-code per product: each product inherits the
workspace-default policy unless it overrides it, classifies its
PII/PHI columns (masked at read time for non-privileged viewers),
and exposes a control-port to erase a data subject. A scheduler job +
admin "scan now" flag deterministic violations into the audit log.

## Preconditions

1. `auth.md` — logged in as admin.
2. `scripts/seed-e2e.py` + `scripts/seed-mesh-demo.py` — provides the
   `demo.sales` / `demo.hr` products with declared columns.

   ```bash
   uv run python scripts/seed-e2e.py
   uv run python scripts/seed-mesh-demo.py
   ```

## Walkthrough

1. **Open the product Governance tab.**
   - Action: `browser_navigate('http://127.0.0.1:8000/data-products/demo/sales?tab=governance')`.
   - Assert: the pane is **visible** (see BUG-128-01) and renders a
     **Policy** editor (retention / encryption_class / residency /
     consent, each defaulting to "inherit"), a **Column
     classifications** card, and a **Control-Port — right-to-be-forgotten**
     card.

2. **Classify a PII column.**
   - Action: in the classifications card fill table `customers`, column
     `email`, classification `pii`; click "Classify".
   - Assert: `POST /api/data-products/demo/sales/classifications` → 200;
     the list shows `customers.email · pii · mask: partial`.

3. **Right-to-be-forgotten confirm modal.**
   - Action: fill subject column `customer_id`, subject value `42`; the
     "Erase subject…" button enables; click it.
   - Assert: a Bootstrap modal opens (`:class="{ 'd-block show': … }"`)
     reading "Confirm erasure — Permanently delete all rows where
     customer_id = 42 … This cannot be undone." Click "Cancel" (do not
     execute the destructive erase in a replay).

4. **Workspace default + compliance scan.**
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/governance')`.
   - Assert: a "Workspace default policy" form + "Save default policy"
     + "Run scan now".
   - Action: click "Run scan now".
   - Assert: a status line "Scanned N product(s), found M violation(s)."
     (M = 0 on the clean seed; to force a violation, set a low retention
     or leave a PII-looking column unclassified.) Violations are written
     to the audit log as `policy.compliance_violation` and surface on
     each product's Governance tab.

## Found bugs

- **BUG-128-01** ✅ Fixed — the product **Governance tab rendered
  nothing** when selected. Root cause: the Contract-tab partial
  [`tab_contract.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/_partials/data_product/tab_contract.html)
  was missing its closing `</div>`, so every tab pane declared after it
  (Diff, Lineage, Compliance, **Governance**, Interop, Activity) was
  parsed as a *child* of the Contract pane. On `?tab=governance` the
  parent Contract pane is `display:none`, so the Governance pane was
  hidden (`offsetParent === null`, `clientHeight === 0`); on
  `?tab=contract` all of them rendered stacked. Fixed by adding the
  missing closing `</div>` so the panes are siblings again.

## Anti-goals

- Honest split: retention is **monitored**, PII masking +
  right-to-be-forgotten are **enforced**; encryption-class, residency,
  and consent are **declarations** surfaced in the discovery contract
  and the compliance scan, not enforced at runtime.
- Policy-compliance violations go to the **audit log** (deterministic),
  not the anomaly inbox (statistical / ack-only).
