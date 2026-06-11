# Access requests & certifications walkthrough

> **Mode:** `browser` · **Surface:** /access-requests + table detail

Exercise the request-for-access loop (request → owner decision →
real grant) and table certification badges.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first.
- Two browser sessions: an admin/owner and a non-admin user
  **without** SELECT on the target table.

## Walkthrough

### Part A — request → approve → access (4 steps)

1. **Request from the table page**.
   - Action: as the non-admin, open the target table's detail page.
   - Assert: a "Request access" button renders (the preview is
     gated); clicking opens the justification modal; submit with a
     short reason.
   - Assert: button flips to a disabled "Access requested" state;
     the owner receives a bell notification.

2. **Decide**.
   - Action: as the owner/admin, open `/access-requests`, tab
     "To decide".
   - Assert: the pending row shows requester, table, privileges,
     justification; click **Approve**.

3. **Grant landed**.
   - Action: as the non-admin, run
     `SELECT * FROM <table> LIMIT 1` in `/sql`.
   - Assert: rows return (the approval executed a real UC grant);
     `/access-requests` "My requests" shows status `approved`; a
     bell notification announced it.

4. **Deny path** (second table or second user): deny with a note →
   requester sees `denied` + the note; no grant happens.

### Part B — certifications (2 steps)

5. **Certify**.
   - Action: as owner/admin on the table page, set certification
     → "certified".
   - Assert: a green "Certified" badge renders beside the title.

6. **Deprecate**.
   - Action: switch to "deprecated" with a note.
   - Assert: warning badge plus a deprecation banner carrying the
     note; clearing removes both.
