"use client";

import { ChevronRight, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

/**
 * Shape of a single sidebar navigation entry. The concrete list is injected by
 * the consuming app (see the dashboard `nav-items.ts`), keeping this layout
 * shell free of app-specific routes.
 */
export type NavItemDef = {
  key: string;
  href: string;
  /** Leading icon. Optional: secondary (child) entries render without one. */
  icon?: LucideIcon;
  /** Highlight only on an exact path match (e.g. a "back" entry whose href is a
   *  parent of the current route and so must not stay active on children). */
  exact?: boolean;
  /** Render as a compact back command (e.g. "All apps"): quieter than the
   *  section entries, never marked active. */
  back?: boolean;
  /** Secondary navigation, expanded/collapsed by clicking the parent. */
  children?: NavItemDef[];
};

type NavItemProps = {
  item: NavItemDef;
  /** Called after a destination is selected (for example, to close a drawer). */
  onNavigate?: () => void;
};

function matchesPath(item: NavItemDef, pathname: string): boolean {
  if (item.exact || item.href === "/dashboard") {
    return pathname === item.href;
  }
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

export function NavItem({ item, onNavigate }: NavItemProps) {
  if (item.back) {
    return <BackNavLink item={item} onNavigate={onNavigate} />;
  }
  if (item.children?.length) {
    return <NavGroup item={item} onNavigate={onNavigate} />;
  }
  return <NavLink item={item} onNavigate={onNavigate} />;
}

/**
 * A "back" command. Shares the section entries' geometry and hover treatment
 * (same icon column, inset, radius, and ink-wash fill) so it belongs to the
 * same family, but steps down in type scale and tone — it's a command, not a
 * destination, so it also never gets an active state.
 */
function BackNavLink({ item, onNavigate }: NavItemProps) {
  const t = useTranslations("dashboard.nav");
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className="group mb-2 flex items-center gap-3 rounded-xl px-3 py-2 text-md font-medium text-ink-500 transition-colors hover:bg-ink-wash hover:text-ink-900"
    >
      {Icon ? (
        <Icon
          className="size-5 shrink-0 transition-transform duration-150 group-hover:-translate-x-0.5"
          aria-hidden
        />
      ) : null}
      <span className="truncate">{t(item.key)}</span>
    </Link>
  );
}

function NavLink({ item, onNavigate }: NavItemProps) {
  const pathname = usePathname();
  const t = useTranslations("dashboard.nav");
  const isActive = matchesPath(item, pathname);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={isActive ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-xl px-3 py-2.5 text-lg transition-colors",
        isActive
          ? "bg-brand-soft font-semibold text-brand"
          : "font-medium text-ink-700 hover:bg-ink-wash hover:text-ink-900",
      )}
    >
      {Icon ? <Icon className="size-5 shrink-0" aria-hidden /> : null}
      <span>{t(item.key)}</span>
    </Link>
  );
}

/**
 * A parent entry whose click toggles its secondary nav rather than navigating.
 * Starts expanded when the current route is already inside the section, so a
 * deep link reveals where you are; thereafter the user controls it.
 */
function NavGroup({ item, onNavigate }: NavItemProps) {
  const pathname = usePathname();
  const t = useTranslations("dashboard.nav");
  const sectionActive =
    matchesPath(item, pathname) ||
    item.children?.some((child) => matchesPath(child, pathname));
  const [open, setOpen] = useState(sectionActive);
  const Icon = item.icon;

  return (
    <div className="flex flex-col gap-0.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={cn(
          "flex items-center gap-3 rounded-xl px-3 py-2.5 text-lg transition-colors",
          sectionActive
            ? "font-semibold text-ink-900 hover:bg-ink-wash"
            : "font-medium text-ink-700 hover:bg-ink-wash hover:text-ink-900",
        )}
      >
        {Icon ? <Icon className="size-5 shrink-0" aria-hidden /> : null}
        <span className="flex-1 text-left">{t(item.key)}</span>
        <ChevronRight
          className={cn(
            "size-4 shrink-0 text-ink-400 transition-transform",
            open && "rotate-90",
          )}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="flex flex-col gap-0.5">
          {item.children?.map((child) => (
            <SubNavItem key={child.key} item={child} onNavigate={onNavigate} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SubNavItem({ item, onNavigate }: NavItemProps) {
  const pathname = usePathname();
  const t = useTranslations("dashboard.nav");
  const isActive = matchesPath(item, pathname);

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={isActive ? "page" : undefined}
      className={cn(
        "flex items-center rounded-xl py-2 pl-11 pr-3 text-md transition-colors",
        isActive
          ? "font-semibold text-brand"
          : "font-medium text-ink-500 hover:bg-ink-wash hover:text-ink-900",
      )}
    >
      <span>{t(item.key)}</span>
    </Link>
  );
}
