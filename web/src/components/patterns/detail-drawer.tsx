"use client";

import { type ReactNode, useEffect } from "react";

import { Drawer, DrawerShell } from "@/components/ui/drawer";
import { Sheet, SheetShell } from "@/components/ui/sheet";
import { useIsDesktop } from "@/hooks/use-media-query";
import { useDrawerPresenceStore } from "@/stores/drawer-presence-store";

type DetailDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  /** Detail body. Scrolls within the drawer when it overflows. */
  children: ReactNode;
  footer?: ReactNode;
  /** Accessible label for the close button. */
  closeLabel?: string;
  contentClassName?: string;
};

/**
 * Responsive detail panel. On desktop it's a Sheet that slides in from the
 * right (a focused detail preview). On mobile it's a real Drawer that slides up
 * from the bottom with drag-to-close and snap heights (`vaul`). Both render the
 * same body and share focus trap / scroll lock / Esc + overlay close.
 */
export function DetailDrawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  closeLabel = "Close",
  contentClassName,
}: DetailDrawerProps) {
  const isDesktop = useIsDesktop();

  // Register presence while open so the app shell scales the background back.
  // Mobile only — the desktop right-side Sheet doesn't push the page back.
  const markOpen = useDrawerPresenceStore((s) => s.open);
  const markClosed = useDrawerPresenceStore((s) => s.close);
  useEffect(() => {
    if (!open || isDesktop) return;
    markOpen();
    return () => markClosed();
  }, [open, isDesktop, markOpen, markClosed]);

  if (isDesktop) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetShell
          side="right"
          title={title}
          titleClassName="text-2xl"
          description={description}
          closeButton
          closeLabel={closeLabel}
          footer={footer}
          contentClassName={contentClassName ?? "w-full sm:max-w-md"}
        >
          {children}
        </SheetShell>
      </Sheet>
    );
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerShell
        title={title}
        titleClassName="text-2xl"
        description={description}
        closeButton
        closeLabel={closeLabel}
        footer={footer}
        snapPoints={[0.6, 1]}
        contentClassName={contentClassName}
      >
        {children}
      </DrawerShell>
    </Drawer>
  );
}
