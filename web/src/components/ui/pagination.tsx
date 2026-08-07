"use client";

import {
  ChevronLeftIcon,
  ChevronRightIcon,
  MoreHorizontalIcon,
} from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Shadcn's standard pagination API ported to the project's tokens with a
 * HeroUI v3 visual treatment:
 *  - `.pagination__content` → flex row with a small gap, no wrapping container.
 *  - `.pagination__link`    → 36px circular hit target, ghost by default,
 *    `bg-brand` + `shadow-action` on the active page (HeroUI's `color="primary"`
 *    + `showShadow` look).
 *  - `:active { scale: 0.97 }` is approximated with Tailwind's `active:scale-95`.
 *
 * Anchors keep the shadcn signature (`href="#"` from the demo) so consumers can
 * use the documented JSX; for local-state pagination, pass `onClick` that calls
 * `preventDefault` before driving setState.
 */

function Pagination({ className, ...props }: React.ComponentProps<"nav">) {
  return (
    <nav
      aria-label="pagination"
      data-slot="pagination"
      className={cn("mx-auto flex w-full justify-center", className)}
      {...props}
    />
  );
}

function PaginationContent({
  className,
  ...props
}: React.ComponentProps<"ul">) {
  return (
    <ul
      data-slot="pagination-content"
      className={cn("inline-flex flex-row items-center gap-1", className)}
      {...props}
    />
  );
}

function PaginationItem({ ...props }: React.ComponentProps<"li">) {
  return <li data-slot="pagination-item" {...props} />;
}

type PaginationLinkProps = {
  isActive?: boolean;
  disabled?: boolean;
  /** Accepted only for API parity with shadcn's `<PaginationLink href="#">`
   *  demo signature — we render a real <button> for accessibility, so the
   *  value is ignored. */
  href?: string;
} & Omit<React.ComponentProps<"button">, "type">;

function PaginationLink({
  className,
  isActive,
  disabled,
  href: _href,
  ...props
}: PaginationLinkProps) {
  return (
    <button
      type="button"
      aria-current={isActive ? "page" : undefined}
      data-slot="pagination-link"
      data-active={isActive}
      disabled={disabled}
      className={cn(
        // Base is a 36×36 circle — page-number tiles use this size as-is.
        // Prev/Next override `w-9` to `w-auto px-3` to host an icon + label.
        "inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-sm font-medium transition-all outline-none select-none active:scale-95",
        "focus-visible:ring-2 focus-visible:ring-brand/40",
        "disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100",
        // HeroUI default-color active fill is a translucent darker gray on top
        // of the footer's light wash — clearly differentiated without using
        // the brand color.
        isActive
          ? "bg-ink-400/30 text-ink-900 hover:bg-ink-400/30"
          : "text-ink-700 hover:bg-ink-400/15 hover:text-ink-900",
        className,
      )}
      {...props}
    />
  );
}

function PaginationPrevious({
  className,
  children,
  ...props
}: React.ComponentProps<typeof PaginationLink>) {
  return (
    <PaginationLink
      aria-label={props["aria-label"] ?? "Go to previous page"}
      className={cn("w-auto gap-1 px-3 text-ink-700", className)}
      {...props}
    >
      <ChevronLeftIcon className="size-4" aria-hidden />
      <span>{children ?? "Prev"}</span>
    </PaginationLink>
  );
}

function PaginationNext({
  className,
  children,
  ...props
}: React.ComponentProps<typeof PaginationLink>) {
  return (
    <PaginationLink
      aria-label={props["aria-label"] ?? "Go to next page"}
      className={cn("w-auto gap-1 px-3 text-ink-700", className)}
      {...props}
    >
      <span>{children ?? "Next"}</span>
      <ChevronRightIcon className="size-4" aria-hidden />
    </PaginationLink>
  );
}

function PaginationEllipsis({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <span
      aria-hidden
      data-slot="pagination-ellipsis"
      className={cn(
        "inline-flex size-9 items-center justify-center text-ink-400",
        className,
      )}
      {...props}
    >
      <MoreHorizontalIcon className="size-4" />
      <span className="sr-only">More pages</span>
    </span>
  );
}

export {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationPrevious,
  PaginationNext,
  PaginationEllipsis,
};
