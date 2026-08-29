import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * GitLab-style sub-group inside a section body: a gray frame with a compact
 * header (bold title, optional description, optional trailing action). Most
 * groups use a white inset body; callers whose children already own their
 * surfaces can omit it to avoid an extra visual layer.
 */
export function GatewaySectionGroup({
  title,
  description,
  action,
  children,
  bodyClassName,
  insetBody = true,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  /** Override the white body's padding (e.g. flush lists). */
  bodyClassName?: string;
  /** Render children directly when they already provide their own surfaces. */
  insetBody?: boolean;
}) {
  return (
    <section
      data-slot="gateway-section-group"
      className="overflow-hidden rounded-3xl bg-table-frame"
    >
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
        <div className="min-w-0 flex-1 basis-52">
          <h3 className="text-sm font-semibold text-ink-900">{title}</h3>
          {description ? (
            <p className="mt-0.5 text-2xs leading-snug text-ink-500">
              {description}
            </p>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </header>
      {insetBody ? (
        <div
          className={cn(
            "mx-1 mb-1 rounded-table-pill bg-surface p-4",
            bodyClassName,
          )}
        >
          {children}
        </div>
      ) : (
        children
      )}
    </section>
  );
}
