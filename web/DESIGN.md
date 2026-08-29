---
name: RPC Gateway Console
description: Light, flat operational console for managing RPC gateway inventory, routing, health, and usage.
colors:
  page-bg: "#f8f8f8"
  surface: "#ffffff"
  brand: "#35abfe"
  brand-hover: "#3bb1fe"
  brand-soft: "rgb(53 171 254 / 0.1)"
  brand-sky: "#35abfe"
  brand-sky-mid: "#3bb1fe"
  brand-sky-highlight: "#56befd"
  brand-sky-end: "#52bdfd"
  ink-900: "#0f172a"
  ink-700: "#334155"
  ink-500: "#64748b"
  ink-400: "#94a3b8"
  ink-wash: "rgb(15 23 42 / 0.04)"
  stripe: "rgb(15 23 42 / 0.022)"
  positive: "#16a34a"
  positive-soft: "rgb(22 163 74 / 0.08)"
  warning: "#d97706"
  warning-soft: "rgb(217 119 6 / 0.08)"
  danger: "#dc2626"
  danger-soft: "rgb(220 38 38 / 0.08)"
  chart-1: "#35abfe"
  chart-2: "#16a34a"
  chart-3: "#d97706"
  chart-4: "#a855f7"
  chart-5: "#06b6d4"
  chart-6: "#ec4899"
  chart-7: "#52bdfd"
  chart-8: "#facc15"
  chart-9: "#6366f1"
  chain-ethereum: "hsl(225 80% 66%)"
  chain-polygon: "hsl(0 0% 50%)"
  chain-bsc: "hsl(46 91% 49%)"
  chain-arbitrum: "hsl(202 90% 55%)"
  chain-optimism: "hsl(0 100% 50%)"
  chain-base: "hsl(217 100% 60%)"
  chain-solana: "hsl(267 100% 64%)"
  chain-bitcoin: "hsl(33 100% 55%)"
  chain-litecoin: "hsl(218 46% 41%)"
  chain-tron: "hsl(357 63% 48%)"
typography:
  display:
    fontFamily: 'var(--font-geist-sans), system-ui, sans-serif'
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: 'var(--font-geist-sans), system-ui, sans-serif'
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: 'var(--font-geist-sans), system-ui, sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  field-label:
    fontFamily: 'var(--font-geist-sans), system-ui, sans-serif'
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.43
  metadata:
    fontFamily: 'var(--font-geist-sans), system-ui, sans-serif'
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.33
  mono:
    fontFamily: '"Maple Mono", "SF Mono", "JetBrains Mono", ui-monospace, monospace'
    fontSize: "16px"
    fontWeight: 500
    lineHeight: 1.5
    fontFeature: '"tnum"'
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  xl: "12px"
  2xl: "16px"
  3xl: "24px"
  table-pill: "20px"
  full: "9999px"
spacing:
  canvas: "32px"
  sidebar: "256px"
  table-row: "48px"
  table-head: "44px"
  table-default-rows: 10
  table-inventory-rows: 12
components:
  button-default:
    backgroundColor: "{colors.brand}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
  button-soft:
    backgroundColor: "{colors.brand-soft}"
    textColor: "{colors.brand}"
    rounded: "{rounded.md}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-700}"
    rounded: "{rounded.md}"
  button-destructive:
    backgroundColor: "{colors.danger}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
  input-default:
    backgroundColor: "{colors.ink-wash}"
    textColor: "{colors.ink-900}"
    rounded: "{rounded.md}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-900}"
    rounded: "{rounded.xl}"
---

# RPC Gateway Console design system

`src/app/globals.css` is the source of truth for runtime tokens; the front matter above is only a machine-readable
summary. This console serves desktop operations workflows, so the interface must stay light, flat, and restrained, and
must prioritize scanning speed and the understandability of action results.

## Visual hierarchy

- `page-bg` is the canvas, `surface` is the working plane, and `ink-wash` marks secondary or recessed areas.
- Group content with spacing and slight tonal differences first; use a border only for a real boundary, and add a
  shadow only for an independent overlay.
- `brand` carries only primary actions, selection, and focus; states use `positive`, `warning`, and `danger` text with
  the matching soft backgrounds.
- Geist is used for interface text; Maple Mono is used only for URLs, IDs, methods, addresses, and comparable numbers.
- Use the existing Tailwind scale and `globals.css` tokens; arbitrary values are prohibited.

One area owns one primary surface. When a child component already has a background, radius, or shadow, the parent must
not add another decorative container. Do not use cards as a substitute for information hierarchy, and do not disguise
read-only information as a disabled input.

## Pages and actions

1. Organize pages by user task and reading order rather than copying the backend object tree.
2. Keep collection actions near the collection and edit actions near the object, and separate dangerous actions from
   settings.
3. Show a small number of important options directly; use Select, Popover, or Drawer for many or infrequent options.
4. The view state uses text, lists, or metadata; form controls appear only after explicitly entering the edit state.
5. Loading, empty, error, dirty, saving, conflict, and destructive confirmation must all have complete states.

Console copy is short and factual. A title names the object and a button names the action; a description explains only
the result or risk and does not repeat the title.

## Tables and row expansion

- A default table reserves 10 rows; Endpoint and Provider inventory reserve and request 12 rows. Keep the blank space
  when there is less data, and reach more data through pagination.
- The table head owns filtering and column visibility; a selected item uses the same background as hover, with no
  added dot or check decoration.
- Filtering and pagination update only the table data area; head, frame, and pagination stay stable, and old data fades
  and becomes non-interactive while a request is in flight.
- Fixed-layout columns must constrain long text; name and URL are separate columns, and the URL is shown on one line,
  truncated to the available space, with a copy action.
- Row expansion uses the full row width and a white active surface while other rows recede to the table frame; do not
  fill the details with nested cards.

Endpoint row expansion contains Endpoint and Bindings:

- Clicking the name expands read-only details; Edit in the list Action opens that row's edit form directly and
  collapses after Save or Cancel, without passing through the details state.
- The Endpoint URL is the primary information: it is shown in full with a persistent copy action.
- Provider, external ID, sync status, last seen, and authentication use compact facts.
- Endpoint ID, Created, and Registry version collapse into a de-emphasized metadata footer.
- Bindings use a flat list; unbinding is completed through a confirmation Dialog.

Provider row expansion contains Provider, Endpoints, and Activity. Credentials are hidden by default; Endpoints scroll
inside the expanded area and Activity uses inline pagination, so no separate details page is created.

## Controls

- Ordinary buttons use `rounded-md`; pills are reserved for explicit filter/segment semantics and are not used for
  ordinary actions.
- Inline edit controls use a borderless light fill, a clear hover change, and a brand focus ring; low-contrast grays
  that look disabled must not be used.
- A copyable value reveals its copy button on hover/focus; the primary URL in Endpoint details may keep the copy
  button persistent.
- A state must always include text and must not rely on color or a dot without semantics.
- Every interaction must support keyboard focus, disabled, loading, error, and long content.

## Motion

Motion only explains a state change and never delays input. Shared values live in `src/lib/motion.ts`; `motion/react`
calls must go through `useMotionPreset()` to handle reduced motion.

| Owner | Scope |
| --- | --- |
| CSS | hover, focus, `data-*` states, and simple row entrances |
| `motion/react` | presence, orchestration, layout, and value interpolation |
| Recharts | in-chart animation |

Enters are usually 200ms, exits 140ms, menus 140ms, route arrival 280ms, and chart drawing 700ms. Table rows may enter
with opacity only; the first stable data set may enter row by row at short intervals, while data replaced after
filtering, pagination, or a refresh only transitions the table body as a whole and does not repeat the per-row
animation. Row expansion is 280ms and collapse is 180ms, and the details, arrow, neighboring rows, and table frame
must start their transitions at the same time. Do not customize durations, curves, or springs at call sites.

## Review checklist

- Can the primary task, secondary tasks, and information hierarchy be recognized within a few seconds?
- Are the view state and the edit state clearly separated?
- Do background, radius, border, and shadow each represent real semantics?
- Do long names, full URLs, credential reveal/hide, copy, empty states, and error recovery all work?
- Are keyboard focus, reduced motion, state text, and contrast complete?
- Are tokens, the component layering, and the shared motion presets reused?
