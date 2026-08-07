"use client";

import { XIcon } from "lucide-react";
import type * as React from "react";
import { useState } from "react";
import { Drawer as DrawerPrimitive } from "vaul";

import { cn } from "@/lib/utils";

/**
 * Mobile-first bottom drawer backed by vaul: drag-to-close, snap points, and
 * gesture momentum that a Sheet can't offer. Pair with {@link DrawerShell} for
 * the standard header / scrolling body / footer skeleton. Sheet stays the
 * desktop detail surface; Drawer is the touch surface.
 */

function Drawer(props: React.ComponentProps<typeof DrawerPrimitive.Root>) {
  return <DrawerPrimitive.Root data-slot="drawer" {...props} />;
}

function DrawerTrigger(
  props: React.ComponentProps<typeof DrawerPrimitive.Trigger>,
) {
  return <DrawerPrimitive.Trigger data-slot="drawer-trigger" {...props} />;
}

function DrawerPortal(
  props: React.ComponentProps<typeof DrawerPrimitive.Portal>,
) {
  return <DrawerPrimitive.Portal data-slot="drawer-portal" {...props} />;
}

function DrawerClose(
  props: React.ComponentProps<typeof DrawerPrimitive.Close>,
) {
  return <DrawerPrimitive.Close data-slot="drawer-close" {...props} />;
}

function DrawerOverlay({
  className,
  ...props
}: React.ComponentProps<typeof DrawerPrimitive.Overlay>) {
  return (
    <DrawerPrimitive.Overlay
      data-slot="drawer-overlay"
      className={cn("fixed inset-0 z-50 bg-black/50", className)}
      {...props}
    />
  );
}

function DrawerContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DrawerPrimitive.Content>) {
  return (
    <DrawerPortal>
      <DrawerOverlay />
      <DrawerPrimitive.Content
        data-slot="drawer-content"
        className={cn(
          "fixed inset-x-0 bottom-0 z-50 mt-24 flex h-auto max-h-dvh flex-col rounded-t-2xl bg-background outline-none",
          className,
        )}
        {...props}
      >
        {/* Grab handle — affordance for the drag gesture. */}
        <DrawerPrimitive.Handle className="mx-auto mt-3 h-1.5 w-12 shrink-0 rounded-full bg-ink-400" />
        {children}
      </DrawerPrimitive.Content>
    </DrawerPortal>
  );
}

function DrawerTitle({
  className,
  ...props
}: React.ComponentProps<typeof DrawerPrimitive.Title>) {
  return (
    <DrawerPrimitive.Title
      data-slot="drawer-title"
      className={cn("font-semibold text-foreground", className)}
      {...props}
    />
  );
}

function DrawerDescription({
  className,
  ...props
}: React.ComponentProps<typeof DrawerPrimitive.Description>) {
  return (
    <DrawerPrimitive.Description
      data-slot="drawer-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

/**
 * Standard drawer skeleton over {@link DrawerContent}: grab handle + bordered
 * header (title + optional description + trailing actions / close) + scrolling
 * body + optional bordered footer. Mirrors `SheetShell`'s slot API so a
 * responsive surface can pass the same `children` to either. Always renders a
 * `DrawerTitle` for a11y.
 *
 * Pass `snapPoints` for multi-height drag (e.g. `[0.6, 1]` — opens at 60%, drag
 * up for full, drag below the lowest snap to dismiss). Omit for plain
 * drag-to-close at content height (better for short content like filters).
 */
function DrawerShell({
  title,
  titleClassName,
  srOnlyTitle = false,
  description,
  headerEnd,
  closeButton = false,
  closeLabel = "Close",
  footer,
  snapPoints,
  contentClassName,
  children,
}: {
  title: React.ReactNode;
  titleClassName?: string;
  srOnlyTitle?: boolean;
  description?: React.ReactNode;
  headerEnd?: React.ReactNode;
  closeButton?: boolean;
  closeLabel?: string;
  footer?: React.ReactNode;
  /** Snap heights (fractions of viewport or `%` strings). Omit for drag-to-close. */
  snapPoints?: (number | string)[];
  contentClassName?: string;
  children: React.ReactNode;
}) {
  // vaul wants controlled snap state when snapPoints is set; start at the first.
  const [activeSnap, setActiveSnap] = useState<number | string | null>(
    snapPoints?.[0] ?? null,
  );

  return (
    <DrawerContent
      className={contentClassName}
      {...(snapPoints
        ? {
            snapPoints,
            activeSnapPoint: activeSnap,
            setActiveSnapPoint: setActiveSnap,
          }
        : {})}
    >
      <div className="flex items-start gap-3 border-b border-ink-wash px-6 py-4">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <DrawerTitle
            className={cn(
              srOnlyTitle
                ? "sr-only"
                : "truncate text-lg font-bold tracking-tight text-ink-900",
              titleClassName,
            )}
          >
            {title}
          </DrawerTitle>
          {description ? (
            <DrawerDescription className="truncate text-sm text-ink-500">
              {description}
            </DrawerDescription>
          ) : (
            <DrawerDescription className="sr-only">{title}</DrawerDescription>
          )}
        </div>
        {headerEnd}
        {closeButton ? (
          <DrawerClose
            aria-label={closeLabel}
            className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-ink-500 transition-colors hover:bg-ink-wash hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            <XIcon className="size-3.5" aria-hidden />
          </DrawerClose>
        ) : null}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5">{children}</div>

      {footer ? (
        <div className="border-t border-ink-wash px-6 py-4">{footer}</div>
      ) : null}
    </DrawerContent>
  );
}

export {
  Drawer,
  DrawerTrigger,
  DrawerPortal,
  DrawerClose,
  DrawerOverlay,
  DrawerContent,
  DrawerShell,
  DrawerTitle,
  DrawerDescription,
};
