# Contextual help icons

 introduces small `bi-info-circle` icons next to the
highest-value anchor points in the web UI — page headers, key tabs,
domain-specific badges. Click an icon and a Bootstrap popover
explains *what this is and why it exists*, with an optional "Learn
more →" link back into this concept guide.

## Anatomy

A help-icon renders through one Jinja macro and one registry entry.

```jinja
{% from "_macros/help_icon.html" import info %}

<h1 class="h3 mb-0">Agent runs{{ info('runs.what-is-a-run') }}</h1>
```

The slug `runs.what-is-a-run` resolves through the Jinja global
`help` (registered once in `pointlessql.api.main`) into a
`HelpEntry` from `pointlessql/web/help.py`.

```python
HELP: dict[str, HelpEntry] = {
 "runs.what-is-a-run": HelpEntry(
 title="What is an agent run?",
 body=(
 "A supervised pipeline execution triggered by an "
 "external runtime (Hermes, OpenShell, cron). Every "
 "operation, tool call, and write is captured in the "
 "audit trail."
 ),
 learn_more="/concepts/agent-runs/",
 ),
...
}
```

## Adding a new help slug

1. **Pick a slug.** Use `<page>.<topic>` lowercase-kebab — e.g.
 `branches.copy-on-write`, `audit.starter-query-badge`. The slug
 is a stable identifier, so prefer descriptive over short.
2. **Add the registry entry.** Append a `HelpEntry` to `HELP` in
 [`pointlessql/web/help.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/web/help.py).
 Keep the body to 1-3 sentences (≤ 280 chars) and the title under
 60 chars — the registry tests enforce both caps.
3. **Drop the icon in the template.** Import the macro at the top
 of the page and call `{{ info('<slug>') }}` immediately after the
 text the icon should annotate. Do **not** wrap the macro inside
 a `<button>` or `<a>` — it already emits a button.
4. **Optional: link to a docs page.** Set `learn_more` to a path
 under [`/docs/`](https://flohofstetter.github.io/PointlesSQL/) —
 the macro prefixes the public docs base URL at render time.
5. **Run the tests.** `uv run pytest tests/test_help_registry.py`
 walks the registry and your new slug; a failing length cap or
 malformed `learn_more` URL surfaces immediately.

## Behaviour

The macro renders a `<button data-bs-toggle="popover">` with
`data-bs-trigger="focus"`, which means Bootstrap dismisses the
popover on outside-click and Escape automatically — no extra JS
listeners are needed. HTMX `boost` swaps re-initialise the
popovers in the new content via the `htmx:afterSwap` hook in
[`frontend/js/help_popovers.js`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/help_popovers.js).

## Out of scope (today)

* **Localisation** — English copy only. The slug schema accepts a
 later `locale` layer without macro refactoring.
* **Inline tutorials** — is single-popover; "take a tour
 of this page" needs its own surface.
* **Help-editor UI** — copy lives in Python. A YAML migration
 becomes interesting once non-developers maintain the strings.
