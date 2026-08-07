"use client";

import { Pin, PinOff } from "lucide-react";
import { useTranslations } from "next-intl";
import type {
  FocusEventHandler,
  HTMLAttributes,
  MouseEventHandler,
  ReactNode,
} from "react";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { NavItem, type NavItemDef } from "./nav-item";

type SidebarProps = {
  /** Navigation entries to render. Injected by the app, not hardcoded here. */
  navItems: readonly NavItemDef[];
  /** Where the brand block links to (the app's home). */
  homeHref?: string;
  /** Identity/account block rendered at the foot of the sidebar. */
  userSlot?: ReactNode;
  pinned?: boolean;
  onTogglePin?: () => void;
  onNavigate?: () => void;
  pinnable?: boolean;
  className?: string;
  onMouseEnter?: MouseEventHandler<HTMLElement>;
  onMouseLeave?: MouseEventHandler<HTMLElement>;
  onFocus?: FocusEventHandler<HTMLElement>;
  onBlur?: FocusEventHandler<HTMLElement>;
} & Pick<HTMLAttributes<HTMLElement>, "aria-label">;

export function Sidebar({
  navItems,
  homeHref = "/dashboard",
  userSlot,
  pinned = true,
  onTogglePin,
  onNavigate,
  pinnable = true,
  className,
  onMouseEnter,
  onMouseLeave,
  onFocus,
  onBlur,
  ...rest
}: SidebarProps) {
  const tBrand = useTranslations("dashboard.wordmark");
  const tSidebar = useTranslations("dashboard.sidebar");
  const ToggleIcon = pinned ? PinOff : Pin;
  const toggleLabel = pinned ? tSidebar("unpin") : tSidebar("pin");

  return (
    <aside
      data-slot="sidebar"
      className={cn(
        "flex h-full w-64 flex-col bg-surface rounded-r-3xl shadow-sidebar",
        className,
      )}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      {...rest}
    >
      <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-4 pt-6">
        <div className="flex w-full items-center justify-between gap-2">
          <Link
            href={homeHref}
            onClick={onNavigate}
            className="-m-1 flex items-center gap-3 rounded-xl p-1 focus-visible:bg-ink-wash focus-visible:outline-none"
          >
            {/* biome-ignore lint/performance/noImgElement: tiny static SVG from public assets; next/image adds no value here. */}
            <img
              aria-hidden
              src="/aurpay-logo.svg"
              alt=""
              width={32}
              height={32}
              decoding="async"
              className="size-8 shrink-0"
            />
            <div className="flex flex-col leading-tight">
              <span className="text-lg font-bold tracking-tight text-ink-900">
                {tBrand("name")}
              </span>
              <span className="text-xs font-medium uppercase tracking-wider text-ink-400">
                {tBrand("caption")}
              </span>
            </div>
          </Link>
          {pinnable && (
            <button
              type="button"
              onClick={onTogglePin}
              aria-label={toggleLabel}
              aria-pressed={pinned}
              title={toggleLabel}
              className="inline-flex size-7 items-center justify-center rounded-md text-ink-400 transition-colors hover:bg-ink-wash hover:text-ink-700 focus-visible:bg-ink-wash focus-visible:outline-none"
            >
              <ToggleIcon className="size-4" aria-hidden />
            </button>
          )}
        </div>
        <nav className="flex w-full flex-col gap-0.5">
          {navItems.map((item) => (
            <NavItem key={item.key} item={item} onNavigate={onNavigate} />
          ))}
        </nav>
      </div>
      {userSlot ? <div className="px-3 pb-4 pt-2">{userSlot}</div> : null}
    </aside>
  );
}
