import { ArrowLeft } from "lucide-react";

import { Link } from "@/i18n/navigation";
import type { LegalDocument } from "@/lib/legal-documents";

export function LegalPage({ document }: { document: LegalDocument }) {
  return (
    <main className="min-h-screen bg-page-bg text-ink-900">
      <header className="border-table-frame border-b bg-surface/90 backdrop-blur">
        <div className="mx-auto flex min-h-16 w-full max-w-7xl items-center justify-between gap-4 px-5 sm:px-8 lg:px-10">
          <Link
            href="/login"
            className="flex items-center gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            <span className="flex size-9 items-center justify-center rounded-lg bg-ink-900 text-md font-bold text-white">
              G
            </span>
            <span className="leading-tight">
              <span className="block text-sm font-semibold tracking-wide uppercase">
                Gateway
              </span>
              <span className="block text-xs text-ink-500">
                RPC control plane
              </span>
            </span>
          </Link>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-7xl gap-10 px-5 py-10 sm:px-8 sm:py-14 lg:grid-cols-[15rem_minmax(0,1fr)] lg:px-10">
        <aside className="hidden lg:block">
          <div className="sticky top-8">
            <p className="mb-4 text-xs font-semibold tracking-wider text-ink-400 uppercase">
              {document.contentsLabel}
            </p>
            <nav aria-label={document.contentsLabel}>
              <ol className="grid gap-1 border-table-frame border-l pl-4">
                {document.sections.map((section) => (
                  <li key={section.id}>
                    <a
                      href={`#${section.id}`}
                      className="block py-1.5 text-sm leading-5 text-ink-500 transition-colors hover:text-brand"
                    >
                      {section.title}
                    </a>
                  </li>
                ))}
              </ol>
            </nav>
          </div>
        </aside>

        <article className="min-w-0 max-w-3xl">
          <Link
            href="/login"
            className="mb-8 inline-flex items-center gap-2 text-sm font-semibold text-ink-500 transition-colors hover:text-brand"
          >
            <ArrowLeft className="size-4" aria-hidden />
            {document.backToSignIn}
          </Link>

          <div className="mb-12 border-table-frame border-b pb-10">
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
              {document.title}
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-ink-500">
              {document.description}
            </p>
            <p className="mt-5 text-sm text-ink-400">
              {document.updatedLabel}: {document.updatedDate}
            </p>
          </div>

          <div className="grid gap-12">
            {document.sections.map((section) => (
              <section id={section.id} key={section.id} className="scroll-mt-8">
                <h2 className="text-2xl font-bold tracking-tight text-ink-900">
                  {section.title}
                </h2>
                <div className="mt-4 grid gap-4 text-md leading-7 text-ink-600">
                  {section.paragraphs.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                  ))}
                  {section.bullets ? (
                    <ul className="grid gap-3 pl-5">
                      {section.bullets.map((item) => (
                        <li
                          key={item}
                          className="list-disc pl-1 marker:text-brand"
                        >
                          {item}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </section>
            ))}
          </div>

          <footer className="mt-14 flex flex-col gap-4 rounded-lg bg-ink-wash p-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold tracking-wider text-ink-400 uppercase">
                {document.companionLabel}
              </p>
              <p className="mt-1 font-semibold text-ink-900">
                {document.companionTitle}
              </p>
            </div>
            <Link
              href={document.companionHref}
              className="inline-flex min-h-10 items-center justify-center rounded-md bg-ink-900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-ink-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-ink-wash"
            >
              {document.companionTitle}
            </Link>
          </footer>
        </article>
      </div>
    </main>
  );
}
