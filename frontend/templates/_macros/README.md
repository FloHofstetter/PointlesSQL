# Macros — Jinja includes catalog

Each file under this folder is a Jinja macro library — small,
reusable HTML fragments imported into templates via:

```jinja
{% from "_macros/<file>.html" import <macro> %}
```

This is for **truly cross-page** reusable patterns.  For page-scoped
fragments use partials under `pages/_partials/<page>/`.  See
[`docs/development/frontend-conventions.md`](../../../docs/development/frontend-conventions.md)
for the macro / partial / inline decision.

## Catalog

| Macro                  | File                      | Signature                                                                                                            | Purpose                                                              |
| ---------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `alert_box`            | `alert_box.html`          | `(variant='danger', title=None, message=None, icon=None, details=None, dismissible=False, classes='')`               | Failure / config-disabled alert with optional `<details>` diagnostics |
| `badge`                | `badge.html`              | `(label, variant='secondary', icon=None, tooltip=None, classes='')`                                                  | Bootstrap badge with optional icon + tooltip                         |
| `button`               | `button.html`             | `(label, variant='primary', icon=None, size=None, type='button', onclick=None, x_on_click=None, disabled=False, classes='', href=None)` | Flexible button or anchor with icon + variant + Alpine `@click` slot |
| `copy_button`          | `copy_button.html`        | `(value, label='Copy', icon='clipboard')`                                                                            | Clipboard-copy icon button                                           |
| `csrf`                 | `csrf.html`               | *(no args; reads `request.state.csrf_token`)*                                                                        | Hidden CSRF input for `<form>` posts                                 |
| `data_table`           | `data_table.html`         | `(table_id=None, classes='', max_height=None, hover=True)` — body via `{% call %}` for `<thead>`/`<tbody>`           | Responsive wrapper + standard `.table` chrome; optional sticky-scroll |
| `detail_drawer`        | `detail_drawer.html`      | `(id, label, title, icon)`                                                                                           | Bootstrap offcanvas drawer trigger + pane                            |
| `entity_actions`       | `entity_actions.html`     | `(kind, ref, source_url, citation)`                                                                                  | Entity dropdown menu (data-product, model, run, …)                   |
| `filter_collapsible`   | `filter_collapsible.html` | `(wrapper_id, summary, expanded=False)`                                                                              | Expandable filter row with summary header                            |
| `help_icon`            | `help_icon.html`          | `(slug)`                                                                                                             | Info-icon with popup; body fetched via `help(slug).body`             |
| `labeled_input`        | `labeled_input.html`      | `(name, label, type='text', id=None, x_model=None, value=None, placeholder=None, required=False, readonly=False, disabled=False, size='sm', classes='', hint=None, autocomplete=None, attrs='', wrapper_classes='mb-3')` | `<input>` with associated `<label for>` for screen-reader announce   |
| `labeled_select`       | `labeled_select.html`     | `(name, label, id=None, x_model=None, options=None, value=None, required=False, disabled=False, size='sm', classes='', hint=None, attrs='', wrapper_classes='mb-3')` — body via `{% call %}` for dynamic options | `<select>` with associated `<label for>`                             |
| `labeled_textarea`     | `labeled_textarea.html`   | `(name, label, id=None, x_model=None, value=None, rows=3, placeholder=None, required=False, readonly=False, disabled=False, size='sm', classes='', hint=None, attrs='', wrapper_classes='mb-3')` | `<textarea>` with associated `<label for>`                           |
| `metadata`             | `metadata.html`           | various: `section_header`, `item`, `code_cell`                                                                       | Metadata-card building blocks                                        |
| `pagination`           | `pagination.html`         | `(total, offset, limit, base_url, query_params)`                                                                     | Server-rendered Bootstrap 5.3 pagination                             |
| `page_help`            | `page_help.html`          | `(slug, title='What is this page?', icon='info-circle')` — body via `{% call %}`                                     | Flush "What is this page?" disclosure accordion                       |
| `permission_link`      | `permission_link.html`    | `(href, granted, icon, label)`                                                                                       | Permission-gated nav link (renders disabled when ungranted)          |
| `state_container`      | `state_container.html`    | `(loading_label='Loading…', error_state='error', empty_state='empty', empty_label='No results.', loading_state='loading')` | Async state wrapper (loading/error/empty); use as `{% call state_container() %}…{% endcall %}` |
| `stat_tiles`           | `stat_tiles.html`         | `(tiles, cols=4)` — each tile dict: `label`, `value`\|`x_text`, `variant`, `hint`                                    | Uniform KPI / metric card grid (static or Alpine-bound values)        |
| `timestamps`           | `timestamps.html`         | `relative_time(dt)`, `abs_time(dt)`                                                                                  | Two-tier date display (relative + absolute tooltip)                  |
| `truncate`             | `truncate.html`           | `(text, max=60, klass='')`                                                                                           | Truncate-with-tooltip for list cells                                 |

## When macro vs partial vs inline

- **Macro** — multi-page reuse, parameterised (`badge`, `button`,
  `pagination`).  Lives in this folder.
- **Partial** — page-scoped, no params, inherits Alpine `x-data`
  scope from the parent template.  Lives in
  `pages/_partials/<page>/`.
- **Inline** — one-off markup, <20 LOC, no reuse expected.  Lives
  where it is rendered.

Promotion rules:

- If a partial gets ≥2 consumers across pages, promote it to the
  flat top-level `frontend/templates/partials/` folder.
- If a partial gets ≥3 page-consumers AND has a parameterisable
  shape, promote it to a macro here.
- If a macro takes >7 args or has >3 conditional branches, split
  it or keep the call-sites inline — a macro that needs a tutorial
  to call correctly is the wrong abstraction.

## Mass-migration of inline call-sites

The `badge` and `button` macros were added during the W4 template-split
wave; the existing ~475 inline `<span class="badge bg-…">` and ~552
inline `<button class="btn …">` call-sites were **deliberately not
mass-migrated**.  The macros land for new templates and for selective
opportunistic migration when touched.  Bulk migration is a separate
follow-up sweep, not a blocker.

## See also

- [Frontend architecture](../../../docs/development/frontend-architecture.md)
- [Frontend conventions](../../../docs/development/frontend-conventions.md)
- [Design tokens](../../../docs/development/design-tokens.md)
