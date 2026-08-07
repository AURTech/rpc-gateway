# Component library rules

This directory is the internal `web/` component library. Components are layered by abstraction, with dependencies
flowing in one direction:

```text
layout/  ->  patterns/  ->  ui/  ->  lib/
```

- **`ui/`** contains general token-driven primitives with no business dependencies. Adapt output from `shadcn add` to
  these rules.
- **`patterns/`** contains reusable compositions such as `form-dialog` and `data-table`. It may depend only on `ui/`
  and `lib/`, never route `_components/`.
- **`layout/`** contains generic application-shell structures such as `app-shell` and `sidebar`. Navigation, branding,
  and user blocks enter through props rather than hard-coded routes or business data.

Application-specific navigation, account blocks, and page components belong in `src/app/**/_components/` and enter
these layers as data or slots. Each shared layer should be reusable in a template repository without modification.

## Component structure

- Use ordinary function components with `React.ComponentProps<...>` prop forwarding, including `ref`. React 19 treats
  `ref` as a normal prop; do not use `forwardRef`.
- Define variants with [CVA](https://cva.style) as `xxxVariants = cva(base, { variants, defaultVariants })` and export
  both the component and its variants.
- Add `data-slot="<name>"` to the root. Components with variants also expose `data-variant` and `data-size`.
- Merge classes through `cn()` from `@/lib/utils`. Put caller-supplied `className` last so it can override defaults.

```tsx
function Thing({ className, variant = "default", ...props }: ThingProps) {
  return (
    <div
      data-slot="thing"
      data-variant={variant}
      className={cn(thingVariants({ variant }), className)}
      {...props}
    />
  );
}
```

## Variant and size vocabulary

- **variant**: `default`, `secondary`, `outline`, `ghost`, and `destructive`, plus explicit business variants such as
  `pill-primary`.
- **size**: `xs`, `sm`, `default`, and `lg`, plus the `icon` family.
- **semantic color**: map success, warning, and danger to `positive`, `warning`, and `danger` tokens from
  `globals.css @theme`.

## Token constraints

- Arbitrary Tailwind values such as `rounded-[..]`, `bg-[#..]`, and `text-[..]` are prohibited. Use named tokens from
  `globals.css @theme`. `scripts/lint-no-arbitrary-tw.mjs` enforces this across the project during `pnpm lint`.
- Register new color, radius, and shadow tokens in `globals.css @theme` before using their utilities.
- Chart series colors must set `--chart-N` explicitly.

## Files and exports

- Put one component in each kebab-case file.
- Use named exports, never default exports.
- Use Radix as the only headless layer under the Shadcn/ui convention; do not add a second headless library.

## Component gallery

`src/app/[locale]/dev/components` is available only when `NODE_ENV !== "production"`. When adding a primitive or
pattern, add a gallery example covering its variants, sizes, and relevant disabled, loading, and error states.
