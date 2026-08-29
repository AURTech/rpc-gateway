"use client";

import { motion } from "motion/react";
import { type ReactNode, useEffect, useState } from "react";
import { useMotionPreset } from "@/hooks/use-motion-preset";
import { cn } from "@/lib/utils";
import { useDrawerPresenceStore } from "@/stores/drawer-presence-store";
import { MobileSidebar } from "./mobile-sidebar";
import type { NavItemDef } from "./nav-item";
import { PageTransition } from "./page-transition";
import { Sidebar } from "./sidebar";
import { useSidebarPinned } from "./use-sidebar-pinned";

type AppShellProps = {
  /** Sidebar navigation entries, injected by the consuming app. */
  navItems: readonly NavItemDef[];
  /** Where the sidebar brand block links to. Defaults to /dashboard. */
  homeHref?: string;
  /**
   * Renders the identity/account block. Receives `onOpenChange` so an open
   * account menu can keep the (unpinned) sidebar revealed.
   */
  renderUserSlot?: (args: {
    onOpenChange: (open: boolean) => void;
  }) => ReactNode;
  children: ReactNode;
};

export function AppShell({
  navItems,
  homeHref,
  renderUserSlot,
  children,
}: AppShellProps) {
  const { pinned, toggle: togglePin } = useSidebarPinned();
  const [revealed, setRevealed] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const visible = pinned || revealed || userMenuOpen;

  // When a slide-out detail drawer is open, scale the whole shell back behind
  // it (iOS-style). Scroll is locked while a drawer is open, so we scale around
  // the visible viewport center — expressed in the element's own coordinate
  // space (top edge = page top) — so a scrolled-down page doesn't jump.
  const backgroundScaled = useDrawerPresenceStore((s) => s.openCount > 0);
  const motionPreset = useMotionPreset();
  const [scaleOrigin, setScaleOrigin] = useState<string | undefined>();
  useEffect(() => {
    if (!backgroundScaled) return;
    setScaleOrigin(
      `50% ${Math.round(window.scrollY + window.innerHeight / 2)}px`,
    );
  }, [backgroundScaled]);

  return (
    <motion.div
      className={cn(
        "min-h-screen font-sans bg-page-bg text-ink-900",
        backgroundScaled && "overflow-hidden",
      )}
      style={{ transformOrigin: scaleOrigin }}
      animate={{
        scale: backgroundScaled ? 0.95 : 1,
        borderRadius: backgroundScaled ? 24 : 0,
      }}
      transition={motionPreset.transition({
        type: "spring",
        stiffness: 380,
        damping: 32,
      })}
    >
      <Sidebar
        navItems={navItems}
        homeHref={homeHref}
        userSlot={renderUserSlot?.({ onOpenChange: setUserMenuOpen })}
        pinned={pinned}
        onTogglePin={togglePin}
        className={cn(
          "fixed inset-y-0 left-0 z-30 hidden transition-transform duration-200 ease-out md:flex",
          visible ? "translate-x-0" : "-translate-x-full",
        )}
        onMouseEnter={() => setRevealed(true)}
        onMouseLeave={() => setRevealed(false)}
        onFocus={() => setRevealed(true)}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
            setRevealed(false);
          }
        }}
      />

      {/* Invisible hover hot-zone: lets the user summon the sidebar by drifting
       * to the left edge when unpinned. Accessibility is preserved because the
       * sidebar itself receives keyboard focus events that toggle the same state. */}
      {!pinned && (
        <div
          aria-hidden
          className="fixed inset-y-0 left-0 z-20 hidden w-2 md:block"
          onMouseEnter={() => setRevealed(true)}
        />
      )}

      <MobileSidebar
        navItems={navItems}
        homeHref={homeHref}
        renderUserSlot={renderUserSlot}
      />

      <main
        className={cn(
          "transition-[padding] duration-200 ease-out",
          pinned ? "md:pl-64" : "md:pl-0",
        )}
      >
        {/* Inside the padded wrapper, so the page content travels on arrival
            but the gutter stays put. */}
        <div className="mx-auto max-w-7xl px-4 pb-8 pt-20 sm:px-8 sm:pt-8">
          <PageTransition>{children}</PageTransition>
        </div>
      </main>
    </motion.div>
  );
}
