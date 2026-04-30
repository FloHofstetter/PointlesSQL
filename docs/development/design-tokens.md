# Design tokens

The single source of truth for PointlesSQL's design system, landed
in Sprint 29 as the foundation every later Phase-9 sprint consumes.
Tokens live in [`frontend/css/style.css`](../frontend/css/style.css)
under the `:root` block; this file is the human-facing reference.

Philosophy: one token scale per concern, no magic values in
templates. Prefer a primitive (`.pql-card`, `.pql-stack`, …) over
a Bootstrap utility stack (`card mb-4`, `d-flex flex-column gap-3`)
whenever the intent maps.

## Spacing

A 4-px scale. Use the token that matches a Bootstrap utility you
would have otherwise reached for.

| Token            | rem       | px   | Replaces                |
| ---------------- | --------- | ---- | ----------------------- |
| `--pql-space-1`  | 0.25rem   | 4    | `gap-1`, `m-1`, `p-1`   |
| `--pql-space-2`  | 0.5rem    | 8    | `gap-2`, `m-2`          |
| `--pql-space-3`  | 0.75rem   | 12   | `gap-3`, `p-3`          |
| `--pql-space-4`  | 1rem      | 16   | `mb-3`, default stack   |
| `--pql-space-5`  | 1.5rem    | 24   | `mb-4`, `p-4`, card pad |
| `--pql-space-6`  | 2rem      | 32   | page sections           |
| `--pql-space-7`  | 3rem      | 48   | page hero               |
| `--pql-space-8`  | 4rem      | 64   | major vertical rhythm   |

## Typography

Inter is self-hosted (Latin subset, woff2, OFL-1.1) at
`/static/fonts/inter-regular.woff2` +
`/static/fonts/inter-semibold.woff2`. Regular (400) is preloaded
in `base.html`; SemiBold (600) is fetched on first use.

| Token                 | rem       | Use                 |
| --------------------- | --------- | ------------------- |
| `--pql-text-xs`       | 0.75rem   | metadata, captions  |
| `--pql-text-sm`       | 0.875rem  | body small          |
| `--pql-text-base`     | 1rem      | body                |
| `--pql-text-lg`       | 1.125rem  | emphasised body     |
| `--pql-text-xl`       | 1.25rem   | card header         |
| `--pql-text-2xl`      | 1.5rem    | page section        |
| `--pql-text-3xl`      | 2rem      | page hero           |

- `--pql-font-sans` — `'Inter', system-ui, …`
- `--pql-font-mono` — OS-native mono stack (no webfont)
- `--pql-weight-regular` = 400
- `--pql-weight-semibold` = 600

## Radius

| Token                | Use                                    |
| -------------------- | -------------------------------------- |
| `--pql-radius-sm`    | 0.25rem — tight controls, form inputs  |
| `--pql-radius-md`    | 0.5rem  — cards, panels                |
| `--pql-radius-lg`    | 0.75rem — modal surfaces               |
| `--pql-radius-pill`  | 9999px  — badges, chips                |

## Elevation

Shadows are dark-mode-first; the light-mode override below lightens
them automatically.

| Token                 | Use                                  |
| --------------------- | ------------------------------------ |
| `--pql-elev-0`        | flat — no shadow                     |
| `--pql-elev-1`        | resting card / button                |
| `--pql-elev-2`        | hovered card / dropdown              |
| `--pql-elev-3`        | modal, popover                       |

## Motion

| Token                   | Value    | Use                              |
| ----------------------- | -------- | -------------------------------- |
| `--pql-duration-fast`   | 120ms    | hover tints, icon swaps          |
| `--pql-duration-normal` | 200ms    | disclosure, tab switches         |
| `--pql-duration-slow`   | 320ms    | modal, off-canvas slide-in       |
| `--pql-ease`            | `cubic-bezier(0.2, 0, 0, 1)` | default |

Sprint 36 will wire `@media (prefers-reduced-motion)` to collapse
these to zero. Until then, respect the preference manually in any
rule that animates.

## Semantic colour

Every status-conveying colour ships as a `bg` + `fg` pair so text
meets AA contrast against its own chip. The brand accent
`#76b900` stays untouched.

| Token                     | Dark-mode default                | Light-mode override |
| ------------------------- | -------------------------------- | ------------------- |
| `--pql-color-accent`      | `#76b900`                        | unchanged           |
| `--pql-color-accent-fg`   | `#0b1400`                        | `#ffffff`           |
| `--pql-color-success-bg`  | `rgba(118, 185, 0, 0.18)`        | `#e7f4d0`           |
| `--pql-color-success-fg`  | `#9fd554`                        | `#3d6b00`           |
| `--pql-color-warning-bg`  | `rgba(255, 170, 0, 0.18)`        | `#fff1cc`           |
| `--pql-color-warning-fg`  | `#ffc04d`                        | `#8a5a00`           |
| `--pql-color-danger-bg`   | `rgba(220, 53, 69, 0.20)`        | `#fde2e5`           |
| `--pql-color-danger-fg`   | `#ff7a88`                        | `#a4222e`           |
| `--pql-color-info-bg`     | `rgba(13, 110, 253, 0.20)`       | `#dce8ff`           |
| `--pql-color-info-fg`     | `#7fb1ff`                        | `#0a3a9a`           |
| `--pql-color-neutral-bg`  | `rgba(255, 255, 255, 0.08)`      | `rgba(0,0,0,0.06)`  |
| `--pql-color-neutral-fg`  | `var(--bs-body-color)`           | unchanged           |

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
top margin automatically; use `.pql-card--flush` when a card
wraps a full-bleed list or iframe.

```html
<div class="pql-card">
  <h2 class="h5 mb-2">Columns</h2>
  <p class="text-muted">No columns yet.</p>
</div>
```

### `.pql-badge`

Pill-shaped status chip. Default renders in neutral; modifier
classes map to the semantic palette.

```html
<span class="pql-badge pql-badge--success"><i class="bi bi-check-lg"></i> OK</span>
<span class="pql-badge pql-badge--warning">Deprecated</span>
<span class="pql-badge pql-badge--danger">Failed</span>
<span class="pql-badge pql-badge--info">Beta</span>
```

### Breakpoints

Added in Sprint 35 for the mobile/responsive pass. The tokens are
*reference values only* — CSS `@media` rules cannot consume
`var(…)`, so every media query in `style.css` repeats the literal.
Treat this block as the canonical contract; any literal that drifts
from these values is a bug.

| Token                    | Value    | Used for                                               |
|--------------------------|----------|--------------------------------------------------------|
| `--pql-breakpoint-sm`    | `640px`  | Top-navbar nav-links → sidebar drawer footer; list tables collapse to label/value cards; mobile sort dropdown activates |
| `--pql-breakpoint-md`    | `768px`  | Sidebar switches from `offcanvas-md` drawer to sticky two-column shell; Cmd+K label + keycap trigger replaces the search-icon button; Jupyter "desktop recommended" notice disappears |
| `--pql-breakpoint-lg`    | `1024px` | Reserved — no rule consumes it yet                      |
| `--pql-breakpoint-xl`    | `1280px` | Reserved — no rule consumes it yet                      |

Touch targets switch to ≥ 44 px minimum under `@media (hover: none)`.

## Conventions

- **Templates** — reach for a primitive first, a Bootstrap utility
  second, inline `style=""` never.
- **Components** — any new component under
  `frontend/templates/components/` should consume tokens via
  `var(--pql-*)` rather than hardcoded rems/pixels.
- **New tokens** — extend the scale in `style.css` and document
  them here in the same commit. A token that is not in this table
  does not exist.
- **Font loading** — add new weights as extra `@font-face` blocks
  and keep the combined woff2 budget under 50 kB per page. Preload
  only the weight that is definitely on the critical path.
