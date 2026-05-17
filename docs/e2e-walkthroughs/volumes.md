# Volumes walkthrough

> **Mode:** `browser` · **Phase:** 12.5 · **Surface:** `/volumes` list + `/volumes/{full_name}` detail (upload, convert-to-Delta, delete)

Covers the volumes surface that landed in Sprint 57 (Phase 12.5):
the list page at `/volumes`, the detail page at
`/volumes/{full_name}` with its upload card, file table,
convert-to-Delta button (csv/parquet/json) and per-file delete.
The detail page is a thin Alpine wrapper over the
`/api/volumes/{full_name}/files` REST surface — every UI
interaction translates 1:1 to one of those routes.

## Preconditions

- Stack up via `docker/docker-compose.yml` + `docker/docker-compose.e2e.yml`.
- [`auth.md`](auth.md) ran first — `admin@pql.test` exists and is
  signed in.
- A volume named `demo.sales.uploads` exists in soyuz-catalog
  with `volume_type=MANAGED` and a `file://` storage_location.
  Seed via `scripts/seed-e2e.py` (which calls the soyuz volume
  REST endpoint added in Sprint 57). If the seed predates that
  sprint, recreate the volume manually:
  ```bash
  curl -X POST http://127.0.0.1:8080/api/2.1/unity-catalog/volumes \
       -H 'Content-Type: application/json' \
       -d '{
         "name": "uploads",
         "catalog_name": "demo",
         "schema_name": "sales",
         "volume_type": "MANAGED",
         "storage_location": "file:///app/warehouse/demo/sales/uploads"
       }'
  ```
- A small `hello.csv` to upload from the host
  (`echo 'id,name\n1,alice' > /tmp/hello.csv`).
- Browser: `--browser firefox` per CLAUDE.md.

## Walkthrough

1. **`/volumes` list renders the demo volume.**
   - Action: `browser_navigate('http://127.0.0.1:8000/volumes')`.
   - Assert: page title is `Volumes · PointlesSQL`; the
     `<h1>` reads `Volumes`; the `text-muted` counter shows
     `1 volume visible` (or higher).
   - Assert: the table has a row whose first cell is the
     monospace anchor `demo.sales.uploads`; type badge reads
     `MANAGED`.

2. **Empty-state copy when no volumes exist.**
   - Setup: temporarily rename the seeded volume in soyuz
     (`PATCH /api/2.1/unity-catalog/volumes/demo.sales.uploads`)
     or run against a clean stack.
   - Action: reload `/volumes`.
   - Assert: the empty-state card renders the `bi-inbox` icon
     and the copy "No volumes found.".
   - Cleanup: restore the volume name.

3. **Drill into the detail page.**
   - Action: click the `demo.sales.uploads` anchor.
   - Assert: URL becomes `/volumes/demo.sales.uploads`.
   - Assert: page title is
     `demo.sales.uploads · Volumes · PointlesSQL`.
   - Assert: the `<h1>` shows the full name + `MANAGED` badge.
   - Assert: the Metadata card lists `Storage`, `Owner`, `Comment`
     in a `<dl class="row">`; storage is a monospace
     `file://`-URI.

4. **Empty volume shows the "Volume is empty" sub-card.**
   - Assert: the Files card renders the muted `<div>` with copy
     "Volume is empty." (template `x-if="files.length === 0"`).
   - Assert: no `<table>` is rendered yet.

5. **Upload `hello.csv` from the host.**
   - Action: in the Upload card, click the file input and
     select `/tmp/hello.csv`.
   - Action: assert `x-model="uploadPath"` auto-fills with the
     basename `hello.csv` (the `onFileChange` handler does this).
   - Action: click `Upload`.
   - Assert: the spinner appears for ≤2 s, then disappears.
   - Assert: the Files table now has one row; first column shows
     the monospace path `hello.csv`; size ≥ 1 byte.
   - Assert: a `Convert to Delta` button is visible on that row
     (csv is in the convertible suffix list).
   - Action: `browser_network_requests()` — confirm a
     `POST /api/volumes/demo.sales.uploads/files` returned 201.

6. **Convert-to-Delta turns the CSV into a Delta table.**
   - Action: click `Convert to Delta` on the `hello.csv` row.
   - Assert: a confirmation modal opens (or a toast appears) and
     a `POST /api/volumes/demo.sales.uploads/convert-to-delta`
     fires; response is 200.
   - Action: `browser_navigate('http://127.0.0.1:8000/catalogs/demo/schemas/sales')`.
   - Assert: a new table with a name derived from `hello` (the
     converter strips the suffix) appears in the schema's table
     list; the type badge reads `MANAGED`.

7. **Delete the uploaded file.**
   - Action: navigate back to `/volumes/demo.sales.uploads`.
   - Action: click the trash icon on the `hello.csv` row.
   - Assert: a `DELETE /api/volumes/demo.sales.uploads/files/hello.csv`
     fires; response is 204.
   - Assert: the row disappears; the Files card returns to the
     empty state.

8. **Non-convertible suffix has no Convert button.**
   - Action: re-upload a `notes.txt` file (any plain-text body).
   - Assert: the new row has the trash icon but the Convert
     button is hidden (`isConvertible(file)` returns `false`).

9. **Back-button returns to the volumes list.**
   - Action: click the `Back` button (`<a href="/volumes">`) in
     the detail page header.
   - Assert: URL becomes `/volumes`; the page renders the table
     again.

10. **REST shape parity — `/api/volumes/{fqn}/files` matches the UI.**
    - Action: `browser_evaluate('() => fetch("/api/volumes/demo.sales.uploads/files").then(r => r.json())')`.
    - Assert: returned object has key `files`; each entry has
      `path` (string) and `size_bytes` (number).
    - Assert: re-rendering the page sets `Alpine.store` with the
      same shape (peek via
      `browser_evaluate('() => document.querySelector("[x-data]").__x.$data.files')`).

## Playwright MCP script

```text
1. browser_navigate /volumes
2. browser_click "demo.sales.uploads"
3. browser_file_upload /tmp/hello.csv
4. browser_click "Upload"
5. browser_wait_for "hello.csv"
6. browser_click "Convert to Delta"
7. browser_navigate /catalogs/demo/schemas/sales  ; assert hello-table visible
8. browser_navigate /volumes/demo.sales.uploads
9. browser_click ".bi-trash"
10. browser_navigate /volumes
```

## Found bugs

_None recorded yet — first replay is part of the Phase 41
Playwright-coverage pass._
