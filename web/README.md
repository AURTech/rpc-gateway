# Frontend architecture

This is the frontend architecture entry point. It records stable layers and dependency boundaries. Business pages and
interactions remain next to their routes.

## Layers and dependency direction

```text
app/[locale]/**            Pages and layouts; route-specific UI in _components/
  ↓
hooks/                     TanStack Query wrappers
  ↓
api/                       Request functions, Zod schemas, and derived types
  ↓
lib/                       Utilities, query client, and site configuration
```

- `src/api/client.ts` is the shared request entry point. `src/api/<domain>/client.ts` groups request functions, Zod
  schemas, and derived types by domain.
- The request layer parses the shared response envelope and validates returned values. Components do not repeat
  response parsing.
- `src/hooks/use-*.ts` wraps queries with TanStack Query. Pages do not call `src/api/*` directly.

## Routing

Pages live under `src/app/[locale]/**`. `src/i18n/routing.ts` defines the English-only locale contract, and
`src/middleware.ts` matches and rewrites locale-prefixed routes. The project keeps Edge Middleware because OpenNext
does not support the default Node.js Proxy runtime in Next.js 16.

## State and context

Providers are assembled in `src/app/providers.tsx`:

- `NextIntlClientProvider` supplies English messages.
- `QueryClientProvider` manages server-data caching in the client.
- `next-themes` manages the theme with `defaultTheme="light"`; `globals.css` currently defines only light tokens.
- Zustand stores short-lived interaction state, not server data.

## UI component boundaries

```text
layout/  ->  patterns/  ->  ui/  ->  lib/
```

- `src/components/ui/*` contains token-driven primitives with no business dependencies.
- `src/components/patterns/*` contains reusable patterns composed from UI primitives.
- `src/components/layout/*` contains the shared application shell and navigation skeleton. Routes and business data
  enter through props.
- Private business components live in `_components/` under the relevant route.

Dependencies flow only in the direction shown above. Shared layers must not import route `_components/`. See
[`src/components/README.md`](./src/components/README.md) for detailed rules. `src/app/globals.css` is the design-token
source of truth.

Use the `components.json` and Shadcn/ui generation conventions when adding primitives.

## Internationalization

The console currently exposes English only. Messages live in `src/locales/en/*.json`, and `src/i18n/messages.ts` loads
the English bundle. Any future locale addition must update routing, the locale layout, message resources, tests, and
legal document alternates together.

## Tests

- `src/**/*.test.ts(x)` contains unit and component tests.
- `src/test/setup.ts` configures the global Vitest environment.
- Tests cover API clients, hooks, utilities, and component behavior directly. There is no shared MSW handler layer.

## Build and deployment

When using the same-origin `/api` proxy, `NEXT_PUBLIC_API_BASE_URL=/api` and an absolute `API_PROXY_TARGET` must both be
configured. Optional Cloudflare Access service-token credentials are forwarded only by the server and never enter the
browser bundle.

OpenNext writes `.open-next/`. `wrangler.jsonc` points to its Worker entry point and static assets binding. Production
domains, the API target, and Cloudflare Access credentials are not committed; ignored build environments and Worker
secrets supply them.
