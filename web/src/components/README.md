# Component library

Shared components are organized by abstraction level, with dependencies flowing in one direction:

```text
dashboard/ → layout/ → patterns/ → ui/ → lib/
```

| Directory | Responsibility | May depend on |
| --- | --- | --- |
| `ui/` | Token-driven primitives with no business semantics | `lib/` |
| `patterns/` | Compositions shared across pages | `ui/`, `lib/` |
| `layout/` | Application shell and navigation skeleton | `patterns/`, `ui/`, `lib/` |
| `dashboard/` | Business components reused across dashboard pages | All layers above |

Single-route components belong in `src/app/**/_components/`. `ui/`, `patterns/`, and `layout/` must not depend on
`dashboard/` or on route components. The root of the component directory keeps only full-page components that are
shared by multiple App Router entries and do not belong to the layers above.

## Writing components

- Use ordinary function components and `React.ComponentProps<...>` to forward native props; React 19 does not need
  `forwardRef`.
- Use kebab-case file names and named exports.
- Set `data-slot` on the root element; components with variants also set `data-variant` and `data-size`.
- Merge classes through `cn()`, with caller-supplied `className` passed last.
- Use CVA for primitives with multiple variants; prefer reusing the `default`, `secondary`, `outline`, `ghost`,
  `destructive`, and `soft` variants, and the `xs`, `sm`, `default`, `lg`, and `icon-*` sizes.
- Primitives mainly use Radix; `combobox.tsx` uses Base UI. Check the existing primitives before adding a dependency.

## Visual constraints

- Arbitrary Tailwind values are prohibited; register new colors, sizes, radii, or shadows in `src/app/globals.css`
  first.
- Use the `positive`, `warning`, and `danger` tokens for states, and `--chart-N` for chart series.
- Every background, radius, padding, and shadow must represent one semantic layer. Do not wrap a decorative surface
  around a child of an existing surface.
- Keep business actions close to their target, and collection actions close to the collection. Do not repeat titles,
  descriptions, or actions between parent and child components.
- Show a small number of important options directly; use Select, Popover, or Drawer for many or infrequent options.
- Route-specific edit state, request logic, and copy stay in the route `_components/` and must not sink into
  primitives.

## Delivery

When adding or changing a primitive, check keyboard focus, disabled, loading, error, long text, and reduced-motion
states. The development component gallery lives in `src/app/[locale]/dev/components` and is reachable only outside
production. See [`../../DESIGN.md`](../../DESIGN.md) for the complete visual rules.
