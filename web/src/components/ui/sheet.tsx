"use client";

import { XIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Dialog as SheetPrimitive } from "radix-ui";
import type * as React from "react";
import { createContext, useContext, useState } from "react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import {
  sheetContentVariants,
  sheetOverlayTransition,
  sheetSpring,
} from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Radix Dialog-backed sheet with motion-driven slides (replaces tw-animate-css).
 * Radix keeps the dialog semantics — focus trap, scroll lock, Esc/overlay
 * close — while `AnimatePresence` + `forceMount` let the spring enter/exit play
 * before unmount. Use controlled (`open` + `onOpenChange`); the open state is
 * shared via context so `SheetContent` can drive the presence.
 */

const SheetContext = createContext<{ open: boolean }>({ open: false });

/**
 * Normalises controlled + uncontrolled open state into a single source of
 * truth. The context must always hold the *real* open value because
 * `SheetContent` keys its `AnimatePresence` off it — relying solely on a
 * `open` prop would make `defaultOpen` / trigger-only usage render nothing.
 */
function Sheet({
  open,
  defaultOpen,
  onOpenChange,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Root>) {
  const isControlled = open !== undefined;
  const [internalOpen, setInternalOpen] = useState(defaultOpen ?? false);
  const actualOpen = isControlled ? open : internalOpen;

  const handleOpenChange = (next: boolean) => {
    if (!isControlled) setInternalOpen(next);
    onOpenChange?.(next);
  };

  return (
    <SheetContext.Provider value={{ open: actualOpen }}>
      <SheetPrimitive.Root
        data-slot="sheet"
        open={actualOpen}
        onOpenChange={handleOpenChange}
        {...props}
      />
    </SheetContext.Provider>
  );
}

function SheetTrigger({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Trigger>) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />;
}

function SheetClose({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Close>) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />;
}

function SheetPortal({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Portal>) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />;
}

function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  closeLabel = "Close",
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & {
  side?: "top" | "right" | "bottom" | "left";
  showCloseButton?: boolean;
  /** Accessible label for the built-in close button (pass an i18n string). */
  closeLabel?: string;
}) {
  const { open } = useContext(SheetContext);
  const motionPreset = useMotionPreset();

  return (
    <SheetPortal forceMount>
      <AnimatePresence>
        {open && (
          <SheetPrimitive.Overlay key="overlay" asChild forceMount>
            <motion.div
              data-slot="sheet-overlay"
              className="fixed inset-0 z-50 bg-black/50"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={motionPreset.transition(sheetOverlayTransition)}
            />
          </SheetPrimitive.Overlay>
        )}
        {open && (
          <SheetPrimitive.Content key="content" asChild forceMount {...props}>
            <motion.div
              data-slot="sheet-content"
              className={cn(
                "fixed z-50 flex flex-col gap-4 bg-background shadow-lg",
                // Round only the edge(s) that face into the viewport; the side
                // flush against the screen edge stays square. Overridable via
                // `className`.
                side === "right" &&
                  "inset-y-0 right-0 h-full w-3/4 rounded-l-2xl sm:max-w-sm",
                side === "left" &&
                  "inset-y-0 left-0 h-full w-3/4 rounded-r-2xl sm:max-w-sm",
                side === "top" && "inset-x-0 top-0 h-auto rounded-b-2xl",
                side === "bottom" && "inset-x-0 bottom-0 h-auto rounded-t-2xl",
                className,
              )}
              variants={sheetContentVariants(side)}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={motionPreset.transition(sheetSpring)}
            >
              {children}
              {showCloseButton && (
                <SheetPrimitive.Close className="absolute top-4 right-4 rounded-xs opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-hidden disabled:pointer-events-none data-[state=open]:bg-secondary">
                  <XIcon className="size-4" />
                  <span className="sr-only">{closeLabel}</span>
                </SheetPrimitive.Close>
              )}
            </motion.div>
          </SheetPrimitive.Content>
        )}
      </AnimatePresence>
    </SheetPortal>
  );
}

/**
 * Standard drawer skeleton over {@link SheetContent}: a bordered header
 * (title + optional description + trailing actions / close), a scrolling body,
 * and an optional bordered footer. Always renders a `SheetTitle` so the dialog
 * is labelled (a11y) without each call site remembering to add one. Consumers
 * own only the body (`children`) and the slot contents.
 */
function SheetShell({
  side = "right",
  title,
  titleClassName,
  srOnlyTitle = false,
  description,
  headerEnd,
  closeButton = false,
  closeLabel = "Close",
  footer,
  contentClassName,
  children,
}: {
  side?: "top" | "right" | "bottom" | "left";
  title: React.ReactNode;
  titleClassName?: string;
  srOnlyTitle?: boolean;
  description?: React.ReactNode;
  /** Trailing header slot — e.g. a reset action. Rendered before the close button. */
  headerEnd?: React.ReactNode;
  /** Render a standard close (X) button at the header end. */
  closeButton?: boolean;
  closeLabel?: string;
  footer?: React.ReactNode;
  contentClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <SheetContent
      side={side}
      showCloseButton={false}
      className={cn("gap-0 p-0", contentClassName)}
    >
      <div className="flex items-start gap-3 border-b border-ink-wash px-6 py-4">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <SheetTitle
            className={cn(
              srOnlyTitle
                ? "sr-only"
                : "truncate text-lg font-bold tracking-tight text-ink-900",
              titleClassName,
            )}
          >
            {title}
          </SheetTitle>
          {description ? (
            <SheetDescription className="truncate text-sm text-ink-500">
              {description}
            </SheetDescription>
          ) : (
            <SheetDescription className="sr-only">{title}</SheetDescription>
          )}
        </div>
        {headerEnd}
        {closeButton ? (
          <SheetClose
            aria-label={closeLabel}
            className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-ink-500 transition-colors hover:bg-ink-wash hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            <XIcon className="size-3.5" aria-hidden />
          </SheetClose>
        ) : null}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5">{children}</div>

      {footer ? (
        <div className="border-t border-ink-wash px-6 py-4">{footer}</div>
      ) : null}
    </SheetContent>
  );
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-1.5 p-4", className)}
      {...props}
    />
  );
}

function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn("mt-auto flex flex-col gap-2 p-4", className)}
      {...props}
    />
  );
}

function SheetTitle({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn("font-semibold text-foreground", className)}
      {...props}
    />
  );
}

function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetShell,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
};
