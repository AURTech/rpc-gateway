import {
  ArrowLeft,
  BarChart3,
  Boxes,
  LayoutDashboard,
  Settings,
  Users,
  Waypoints,
} from "lucide-react";
import type { NavItemDef } from "@/components/layout/nav-item";

/**
 * Secondary nav under Settings; the parent toggles it open, the children link
 * to the pages. Profile is the section index (`exact`, so it doesn't stay lit
 * on sub-routes). Children render without icons.
 * Admins receive a separate system-configuration group for platform controls.
 */
const SETTINGS_CHILDREN: readonly NavItemDef[] = [
  { key: "settingsProfile", href: "/dashboard/settings", exact: true },
  { key: "settingsSecurity", href: "/dashboard/settings/security" },
  {
    key: "settingsTokens",
    href: "/dashboard/settings/personal-access-tokens",
  },
];

function settingsNavItem(): NavItemDef {
  return {
    key: "settings",
    href: "/dashboard/settings",
    icon: Settings,
    exact: true,
    children: [...SETTINGS_CHILDREN],
  };
}

const ADMIN_NAV_ITEMS: readonly NavItemDef[] = [
  { key: "accounts", href: "/dashboard/accounts", icon: Users },
] as const;

const PRIMARY_NAV: readonly NavItemDef[] = [
  { key: "overview", href: "/dashboard", icon: LayoutDashboard, exact: true },
  { key: "apps", href: "/dashboard/apps", icon: Boxes },
  { key: "endpoints", href: "/dashboard/endpoints", icon: Waypoints },
  { key: "usage", href: "/dashboard/usage", icon: BarChart3 },
  { key: "settings", href: "/dashboard/settings", icon: Settings },
] as const;

/**
 * Segments under `/dashboard/apps/` that are pages of their own rather than an
 * app id. Without this, the create flow at `/dashboard/apps/new` would read as
 * an app named "new" and swap the sidebar for that non-existent app's sections.
 */
const RESERVED_APP_SEGMENTS: ReadonlySet<string> = new Set(["new"]);

/**
 * The app id the given route belongs to, or null when it isn't inside a
 * specific app. Creating an app happens under Apps, not inside one, so the
 * reserved segments resolve to null and keep the global sidebar.
 */
export function appIdFromPathname(pathname: string): string | null {
  const segment = pathname.match(/^\/dashboard\/apps\/([^/]+)/)?.[1];
  if (!segment || RESERVED_APP_SEGMENTS.has(segment)) return null;
  return segment;
}

/**
 * Alchemy-style contextual nav. At the top level the sidebar shows the global
 * dashboard entries; gateways have no standalone page — they live inside an
 * app. Once you're inside a specific app (`/dashboard/apps/<id>`) the sidebar
 * becomes that app's own navigation: a back-to-apps entry plus the app's
 * sections; the global entries are hidden until you go back. Gateway
 * management remains a tab within Overview.
 */
export function buildDashboardNav({
  isAdmin,
  appId,
}: {
  isAdmin: boolean;
  /** The current app id when inside `/dashboard/apps/<id>`, else null. */
  appId: string | null;
}): NavItemDef[] {
  const withSettingsChildren = (items: readonly NavItemDef[]) =>
    items.map((item) => (item.key === "settings" ? settingsNavItem() : item));

  if (appId) {
    // Inside an app: the whole sidebar is scoped to it. The back-to-apps entry
    // renders as a distinct "back" command (muted, compact, set apart from the
    // section nav). Overview is the app home at the bare `/apps/<id>` route;
    // `exact` keeps it off the sub-routes. Usage and Settings are separate app
    // sections; Settings expands to General and Access keys, while Overview
    // owns both setup and gateway management.
    return [
      {
        key: "backToApps",
        href: "/dashboard/apps",
        icon: ArrowLeft,
        back: true,
      },
      {
        key: "appOverview",
        href: `/dashboard/apps/${appId}`,
        icon: LayoutDashboard,
        exact: true,
      },
      {
        key: "appUsage",
        href: `/dashboard/apps/${appId}/usage`,
        icon: BarChart3,
      },
      {
        key: "appSettings",
        href: `/dashboard/apps/${appId}/settings`,
        icon: Settings,
        exact: true,
        children: [
          {
            key: "appSettingsGeneral",
            href: `/dashboard/apps/${appId}/settings`,
            exact: true,
          },
          {
            key: "appSettingsAccessKeys",
            href: `/dashboard/apps/${appId}/settings/access-keys`,
          },
        ],
      },
    ];
  }

  // Top level: gateways have no standalone entry — they live inside an app.
  const dashboardNav = isAdmin
    ? [
        ...PRIMARY_NAV.filter((item) => item.key !== "settings"),
        ...ADMIN_NAV_ITEMS,
        settingsNavItem(),
      ]
    : [...PRIMARY_NAV];

  return withSettingsChildren(dashboardNav);
}
