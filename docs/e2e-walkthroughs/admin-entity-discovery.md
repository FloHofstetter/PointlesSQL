# Admin entity-discovery walkthrough

> **Mode:** `browser` · **Surface:** /admin/entity-discovery

End-to-end exercise of the auto-discovery review queue: list view,
accept / reject / defer actions, run-now button.  Tests the
plumbing from `EntityLinkCandidate` rows through the review service
into `EntityLink` (on accept).

## Preconditions

- E2E stack up + `auth.md` ran first (admin signed in).
- At least two `DataProductEntity` rows in the same workspace whose
  PK-overlap or column-similarity scores above the 0.7 threshold,
  so the run-now sweep produces candidates.

## Walkthrough

1. **Land on the entity-discovery page.**
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/entity-discovery')`.
   - Assert: page title contains "Entity discovery · PointlesSQL".
     Heading reads "Entity discovery".  The empty-state row reads
     "No pending candidates." on a fresh workspace.

2. **Run discovery now.**
   - Action: click the "Run now" button (top-right).
   - Assert: the table refreshes.  If pre-seeded entities meet the
     threshold, at least one row appears with Source / Target /
     Confidence / Discovered / Actions columns.

3. **Verify the confidence value formatting.**
   - Action: read each Confidence cell.
   - Assert: numeric values render with two decimals (e.g. `0.85`).

4. **Defer a candidate.**
   - Action: click "Defer" on the first row.
   - Assert: the row disappears from the pending view (the candidate
     is now deferred; the queue refilters automatically).

5. **Reject a candidate.**
   - Action: click "Reject" on another row.
   - Assert: the row disappears; no candidate row was promoted.

6. **Accept a candidate (steward action).**
   - Action: click "Accept" on a third row.
   - Assert: the row disappears.  Optional follow-up: navigate to
     the underlying entity's surface and verify a new EntityLink row
     exists (cross-checked via the discovery envelope on either
     bound product).

## Found bugs

(none at time of writing — fill in during the first live replay)
