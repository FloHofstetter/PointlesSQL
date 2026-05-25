# Design tokens

The single source of truth for PointlesSQL's design system.
Tokens live in [`frontend/css/base.css`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/css/base.css)
under the `:root` block; this file is the human-facing reference.

Philosophy: one token scale per concern, no magic values in
templates. Prefer a primitive (`.pql-card`, `.pql-stack`, …) over
a Bootstrap utility stack (`card mb-4`, `d-flex flex-column gap-3`)
whenever the intent maps.

## Layout constants

Sizing tokens for the page chrome.  `@media` rules cannot consume
`var(…)`, so any media query that gates on these widths duplicates
the px literal — treat the table below as the contract; a literal
that drifts from these values is a bug.

| Token                         | Value              | Used for                                      |
| ----------------------------- | ------------------ | --------------------------------------------- |
| `--pql-sidebar-width`         | 280px              | left navigation drawer width                  |
| `--pql-topbar-height`         | 56px               | sticky topbar height                          |
| `--pql-icon-rail-width`       | 220px (64px collapsed) | sidebar icon rail; collapsed state via `data-pql-rail-state="collapsed"` |
| `--pql-context-panel-width`   | 240px              | right-side contextual panel                   |
| `--pql-meta-panel-width`      | 280px              | notebook meta drawer width                    |
| `--pql-footer-bar-height`     | 28px               | sticky status footer height                   |

## Spacing

A 4-px scale. Use the token that matches a Bootstrap utility you
would have otherwise reached for.

| Token | rem | px | Replaces |
| ---------------- | --------- | ---- | ----------------------- |
| `--pql-space-1` | 0.25rem | 4 | `gap-1`, `m-1`, `p-1` |
| `--pql-space-2` | 0.5rem | 8 | `gap-2`, `m-2` |
| `--pql-space-3` | 0.75rem | 12 | `gap-3`, `p-3` |
| `--pql-space-4` | 1rem | 16 | `mb-3`, default stack |
| `--pql-space-5` | 1.5rem | 24 | `mb-4`, `p-4`, card pad |
| `--pql-space-6` | 2rem | 32 | page sections |
| `--pql-space-7` | 3rem | 48 | page hero |
| `--pql-space-8` | 4rem | 64 | major vertical rhythm |

## Typography

Inter is self-hosted (Latin subset, woff2, OFL-1.1) at
`/static/fonts/inter-regular.woff2` +
`/static/fonts/inter-semibold.woff2`. Regular (400) is preloaded
in `base.html`; SemiBold (600) is fetched on first use.

| Token | rem | Use |
| --------------------- | --------- | ------------------- |
| `--pql-text-xs` | 0.75rem | metadata, captions |
| `--pql-text-sm` | 0.875rem | body small |
| `--pql-text-base` | 1rem | body |
| `--pql-text-lg` | 1.125rem | emphasised body |
| `--pql-text-xl` | 1.25rem | card header |
| `--pql-text-2xl` | 1.5rem | page section |
| `--pql-text-3xl` | 2rem | page hero |

- `--pql-font-sans` — `'Inter', system-ui, …`
- `--pql-font-mono` — OS-native mono stack (no webfont)
- `--pql-weight-regular` = 400
- `--pql-weight-semibold` = 600

## Radius

| Token | Use |
| -------------------- | -------------------------------------- |
| `--pql-radius-sm` | 0.25rem — tight controls, form inputs |
| `--pql-radius-md` | 0.5rem — cards, panels |
| `--pql-radius-lg` | 0.75rem — modal surfaces |
| `--pql-radius-pill` | 9999px — badges, chips |

## Elevation

Shadows are dark-mode-first; the light-mode override below lightens
them automatically.

| Token | Use |
| --------------------- | ------------------------------------ |
| `--pql-elev-0` | flat — no shadow |
| `--pql-elev-1` | resting card / button |
| `--pql-elev-2` | hovered card / dropdown |
| `--pql-elev-3` | modal, popover |

## Motion

| Token | Value | Use |
| ----------------------- | -------- | -------------------------------- |
| `--pql-duration-fast` | 120ms | hover tints, icon swaps |
| `--pql-duration-normal` | 200ms | disclosure, tab switches |
| `--pql-duration-slow` | 320ms | modal, off-canvas slide-in |
| `--pql-ease` | `cubic-bezier(0.2, 0, 0, 1)` | default |

`responsive.css` wires `@media (prefers-reduced-motion: reduce)` to
collapse these tokens to `0ms` and applies a blanket
`animation-duration: 0ms !important` to every element, so any rule
that respects the duration tokens (or a third-party rule with a
literal duration) gets neutralised automatically.

## Bootstrap variable bridges

A handful of Bootstrap 5.3 CSS custom properties are overridden so
PointlesSQL surfaces inherit the brand accent instead of Bootstrap
defaults.  Components consume these directly rather than redeclaring
brand colour on every surface.

| Token                    | Value                              | Effect                                 |
| ------------------------ | ---------------------------------- | -------------------------------------- |
| `--bs-focus-ring-color`  | `rgba(118, 185, 0, 0.40)` (dark: 0.55) | every form control / button / link picks up the green focus ring instead of Bootstrap's default blue |
| `--bs-focus-ring-width`  | `0.2rem`                           | slightly tighter than Bootstrap's default `0.25rem` |
| `--bs-tertiary-bg`       | inherited per color-mode           | consumed by `.pql-card` for the panel surface |
| `--bs-border-color`      | inherited per color-mode           | consumed by `.pql-card` for the panel border |

`.dropdown-item.active` and `.dropdown-item:active` are also rebound
to the accent (`background-color: var(--pql-color-accent)`,
`color: var(--pql-color-accent-fg)`) so single-select menus render
with the brand colour automatically.

## Semantic colour

Every status-conveying colour ships as a `bg` + `fg` pair so text
meets AA contrast against its own chip. The brand accent
`#76b900` stays untouched.

| Token | Dark-mode default | Light-mode override |
| ------------------------- | -------------------------------- | ------------------- |
| `--pql-color-accent` | `#76b900` | unchanged |
| `--pql-color-accent-fg` | `#0b1400` | `#ffffff` |
| `--pql-color-success-bg` | `rgba(118, 185, 0, 0.18)` | `#e7f4d0` |
| `--pql-color-success-fg` | `#9fd554` | `#3d6b00` |
| `--pql-color-warning-bg` | `rgba(255, 170, 0, 0.18)` | `#fff1cc` |
| `--pql-color-warning-fg` | `#ffc04d` | `#8a5a00` |
| `--pql-color-danger-bg` | `rgba(220, 53, 69, 0.20)` | `#fde2e5` |
| `--pql-color-danger-fg` | `#ff7a88` | `#a4222e` |
| `--pql-color-info-bg` | `rgba(13, 110, 253, 0.20)` | `#dce8ff` |
| `--pql-color-info-fg` | `#7fb1ff` | `#0a3a9a` |
| `--pql-color-neutral-bg` | `rgba(255, 255, 255, 0.08)` | `rgba(0,0,0,0.06)` |
| `--pql-color-neutral-fg` | `var(--bs-body-color)` | unchanged |

## Light mode

Light mode is **prepared** but not wired. Toggle it in DevTools:

```html
<html data-bs-theme="light">
```

All `--pql-color-*` tokens and elevation shadows flip via the
`:root[data-bs-theme="light"]` override block. Templates that stick
to the primitives below will adapt automatically. A later sprint
will add a real toggle and persist the preference.

## Primitives

Four CSS-only primitives absorb the most common Bootstrap utility
stacks. None of them require JavaScript; they cascade through
Bootstrap's theme tokens so dark/light keeps working.

### `.pql-stack`

Vertical flex with a token-sized gap.

```html
<div class="pql-stack">
 <h1>…</h1>
 <p>…</p>
 <form>…</form>
</div>
```

Modifiers: `.pql-stack--tight` (gap = `--pql-space-2`) and
`.pql-stack--loose` (gap = `--pql-space-6`).

### `.pql-cluster`

Horizontal, wrapping, centre-aligned cluster. Replaces
`d-flex flex-wrap gap-2 align-items-center`.

```html
<div class="pql-cluster">
 <span class="pql-badge pql-badge--success">Healthy</span>
 <span class="pql-badge">3 runs</span>
</div>
```

### `.pql-card`

Panel surface with border, radius, padding, and resting elevation.
Replaces `card mb-4 p-4`. Adjacent `.pql-card` siblings get a
top margin automatically.

```html
<div class="pql-card">
 <h2 class="h5 mb-2">Columns</h2>
 <p class="text-muted">No columns yet.</p>
</div>
```

### `.pql-badge`

Pill-shaped status chip. Default renders in neutral; the
`--warning` modifier maps to the warning palette.

```html
<span class="pql-badge"><i class="bi bi-check-lg"></i> OK</span>
<span class="pql-badge pql-badge--warning">Deprecated</span>
```

Semantic variants (`--success`, `--danger`, `--info`) were dropped
during a dead-selector sweep because nothing in the project
consumed them; the call-sites used Bootstrap utility classes
(`badge bg-success`) or scoped per-component styling instead.
If a real consumer appears, re-add the modifier in
[`primitives.css`](../../frontend/css/primitives.css) and document
it here in the same commit.

### Breakpoints

Added for the mobile/responsive pass. The tokens are
*reference values only* — CSS `@media` rules cannot consume
`var(…)`, so every media query in `style.css` repeats the literal.
Treat this block as the canonical contract; any literal that drifts
from these values is a bug.

| Token | Value | Used for |
|--------------------------|----------|--------------------------------------------------------|
| `--pql-breakpoint-sm` | `640px` | Top-navbar nav-links → sidebar drawer footer; list tables collapse to label/value cards; mobile sort dropdown activates |
| `--pql-breakpoint-md` | `768px` | Sidebar switches from `offcanvas-md` drawer to sticky two-column shell; Cmd+K label + keycap trigger replaces the search-icon button; Jupyter "desktop recommended" notice disappears |
| `--pql-breakpoint-lg` | `1024px` | Reserved — no rule consumes it yet |
| `--pql-breakpoint-xl` | `1280px` | Reserved — no rule consumes it yet |

Touch targets switch to ≥ 44 px minimum under `@media (hover: none)`.

## Conventions

- **Templates** — reach for a primitive first, a Bootstrap utility
 second, inline `style=""` never.
- **Components** — any new component under
 `frontend/templates/components/` should consume tokens via
 `var(--pql-*)` rather than hardcoded rems/pixels.
- **New tokens** — extend the scale in `base.css` and document
 them here in the same commit. A token that is not in this table
 does not exist.
- **Font loading** — add new weights as extra `@font-face` blocks
 and keep the combined woff2 budget under 50 kB per page. Preload
 only the weight that is definitely on the critical path.

## See also

- [Frontend architecture](frontend-architecture.md) — stack overview,
  cascade tiers, lazy-load pattern
- [Frontend conventions](frontend-conventions.md) — template/JS/CSS
  layout disciplines
- [`frontend/templates/_macros/README.md`](../../frontend/templates/_macros/README.md) —
  Jinja macro catalog that consumes these tokens
