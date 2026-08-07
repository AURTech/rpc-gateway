"use client";

import { Menu } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { NavItemDef } from "./nav-item";
import { Sidebar } from "./sidebar";

type MobileSidebarProps = {
  navItems: readonly NavItemDef[];
  homeHref?: string;
  renderUserSlot?: (args: {
    onOpenChange: (open: boolean) => void;
  }) => ReactNode;
};

export function MobileSidebar({
  navItems,
  homeHref,
  renderUserSlot,
}: MobileSidebarProps) {
  const [open, setOpen] = useState(false);
  const t = useTranslations("dashboard.sidebar");

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="pill-secondary"
          size="icon"
          className="fixed left-4 top-4 z-40 md:hidden"
          aria-label={t("openNavigation")}
        >
          <Menu className="size-4" aria-hidden />
        </Button>
      </SheetTrigger>
      <SheetContent
        side="left"
        showCloseButton={false}
        className="w-64 bg-transparent p-0"
      >
        <SheetTitle className="sr-only">{t("navigationTitle")}</SheetTitle>
        <SheetDescription className="sr-only">
          {t("navigationDescription")}
        </SheetDescription>
        <Sidebar
          pinnable={false}
          navItems={navItems}
          homeHref={homeHref}
          onNavigate={() => setOpen(false)}
          userSlot={renderUserSlot?.({ onOpenChange: () => {} })}
        />
      </SheetContent>
    </Sheet>
  );
}
