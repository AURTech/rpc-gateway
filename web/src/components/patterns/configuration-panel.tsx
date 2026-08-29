"use client";

import { ChevronRightIcon } from "lucide-react";
import type * as React from "react";
import { useId, useState } from "react";

import { cn } from "@/lib/utils";

function ConfigurationPanel({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="configuration-panel"
      className={cn("min-w-0 divide-y divide-ink-wash", className)}
      {...props}
    />
  );
}

interface ConfigurationSectionProps
  extends Omit<React.ComponentProps<"section">, "title"> {
  title: React.ReactNode;
  description?: React.ReactNode;
  bodyClassName?: string;
  defaultOpen?: boolean;
  variant?: "default" | "plain";
  tone?: "default" | "danger";
}

type ConfigurationSectionVariant = NonNullable<
  ConfigurationSectionProps["variant"]
>;

const configurationSectionContentClassName: Record<
  ConfigurationSectionVariant,
  { frame: string; body: string }
> = {
  default: {
    frame: "rounded-2xl border border-ink-wash bg-table-frame p-2",
    body: "rounded-xl bg-surface p-5 md:p-6",
  },
  plain: { frame: "", body: "" },
};

/** Collapsible settings section with an optional inset presentation layer. */
function ConfigurationSection({
  title,
  description,
  bodyClassName,
  defaultOpen = false,
  variant = "default",
  tone = "default",
  className,
  children,
  ...props
}: ConfigurationSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();
  const contentClassName = configurationSectionContentClassName[variant];

  return (
    <section
      data-slot="configuration-section"
      data-tone={tone}
      className={cn("min-w-0", className)}
      {...props}
    >
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={contentId}
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-start gap-3 px-1 py-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
        >
          <ChevronRightIcon
            aria-hidden
            className={cn(
              "mt-0.5 size-4 shrink-0 text-ink-400 transition-transform",
              open && "rotate-90",
            )}
          />
          <span className="min-w-0">
            <span
              className={cn(
                "block text-lg font-semibold tracking-tight",
                tone === "danger" ? "text-danger" : "text-ink-900",
              )}
            >
              {title}
            </span>
            {description ? (
              <span className="mt-1 block text-sm font-normal leading-relaxed text-ink-500">
                {description}
              </span>
            ) : null}
          </span>
        </button>
      </h2>
      <div
        id={contentId}
        hidden={!open}
        className={cn("mb-6 min-w-0", contentClassName.frame)}
      >
        <div className={cn("min-w-0", contentClassName.body, bodyClassName)}>
          {children}
        </div>
      </div>
    </section>
  );
}

export { ConfigurationPanel, ConfigurationSection };
