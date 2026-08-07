import {
  ArrowRight,
  Boxes,
  LogIn,
  Plug,
  SearchX,
  Settings,
  Waypoints,
} from "lucide-react";

type NotFoundQuickLink = {
  href: string;
  label: string;
  description: string;
  icon: "apps" | "endpoints" | "providers" | "settings";
};

type NotFoundPageProps = {
  statusLabel: string;
  eyebrow: string;
  title: string;
  description: string;
  primaryHref: string;
  primaryLabel: string;
  secondaryHref: string;
  secondaryLabel: string;
  guidanceTitle: string;
  guidanceDescription: string;
  routeHint: string;
  bookmarkHint: string;
  quickLinks: NotFoundQuickLink[];
};

const QUICK_LINK_ICONS = {
  apps: Boxes,
  providers: Plug,
  endpoints: Waypoints,
  settings: Settings,
} as const;

export function NotFoundPage({
  statusLabel,
  eyebrow,
  title,
  description,
  primaryHref,
  primaryLabel,
  secondaryHref,
  secondaryLabel,
  guidanceTitle,
  guidanceDescription,
  routeHint,
  bookmarkHint,
  quickLinks,
}: NotFoundPageProps) {
  return (
    <main className="min-h-screen bg-page-bg px-5 py-8 text-ink-900 sm:px-8 lg:px-10">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] w-full max-w-6xl items-center gap-10 lg:grid-cols-[minmax(0,1fr)_26rem]">
        <section className="flex min-w-0 flex-col gap-9">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-lg bg-ink-900 text-lg font-bold text-white">
              G
            </span>
            <div className="flex min-w-0 flex-col">
              <span className="text-sm font-semibold tracking-wide text-ink-900 uppercase">
                Gateway
              </span>
              <span className="truncate text-sm text-ink-500">
                JSON-RPC console
              </span>
            </div>
          </div>

          <div className="grid gap-6">
            <div className="flex w-fit items-center gap-2 rounded-md bg-brand-soft px-3 py-1.5 text-brand">
              <SearchX className="size-4" aria-hidden />
              <span className="font-mono text-sm font-semibold">
                {statusLabel}
              </span>
              <span className="text-sm font-semibold">{eyebrow}</span>
            </div>

            <div className="flex max-w-prose-narrow flex-col gap-4">
              <h1 className="text-4xl font-bold tracking-tight text-ink-900 sm:text-5xl">
                {title}
              </h1>
              <p className="text-lg leading-7 text-ink-500">{description}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <a
              href={primaryHref}
              className="inline-flex min-h-10 items-center gap-2 rounded-md bg-brand px-4 py-2.5 text-md font-semibold text-white shadow-action transition-colors hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-page-bg"
            >
              {primaryLabel}
              <ArrowRight className="size-4" aria-hidden />
            </a>
            <a
              href={secondaryHref}
              className="inline-flex min-h-10 items-center gap-2 rounded-md border border-table-frame bg-surface px-4 py-2.5 text-ink-700 text-md font-semibold transition-colors hover:bg-ink-wash focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-page-bg"
            >
              <LogIn className="size-4" aria-hidden />
              {secondaryLabel}
            </a>
          </div>
        </section>

        <aside className="min-w-0 rounded-lg bg-surface p-4 shadow-section sm:p-5">
          <div className="flex flex-col gap-5">
            <div className="rounded-md bg-ink-wash p-4">
              <div className="flex items-center justify-between gap-4">
                <span className="text-sm font-semibold text-ink-900">
                  {guidanceTitle}
                </span>
                <span className="rounded-md bg-surface px-2 py-1 font-mono text-2xs font-semibold text-ink-500">
                  {statusLabel}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-ink-500">
                {guidanceDescription}
              </p>
            </div>

            <div className="grid gap-2">
              {[routeHint, bookmarkHint].map((hint) => (
                <div
                  className="flex items-start gap-3 rounded-md px-2 py-2"
                  key={hint}
                >
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-brand" />
                  <span className="text-sm leading-6 text-ink-700">{hint}</span>
                </div>
              ))}
            </div>

            <div className="grid gap-2">
              {quickLinks.map((link) => {
                const Icon = QUICK_LINK_ICONS[link.icon];

                return (
                  <a
                    className="group flex min-h-16 items-center gap-3 rounded-md px-3 py-2.5 transition-colors hover:bg-row-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
                    href={link.href}
                    key={link.href}
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-ink-wash text-ink-500 transition-colors group-hover:bg-surface group-hover:text-brand">
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-ink-900">
                        {link.label}
                      </span>
                      <span className="block truncate text-sm text-ink-500">
                        {link.description}
                      </span>
                    </span>
                    <ArrowRight
                      className="size-4 shrink-0 text-ink-400 transition-transform group-hover:translate-x-0.5 group-hover:text-brand"
                      aria-hidden
                    />
                  </a>
                );
              })}
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
