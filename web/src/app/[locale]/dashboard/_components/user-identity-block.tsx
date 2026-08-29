"use client";

import { BookOpen, ChevronsUpDown, LogOut, Settings } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLogout } from "@/hooks/use-auth";
import { Link, useRouter } from "@/i18n/navigation";
import { useAuthStore } from "@/stores/auth-store";

/** First initial from a display name, falling back to the email. */
function initialsFrom(name: string | null | undefined, email: string): string {
  const source = name?.trim() || email;
  return Array.from(source)[0]?.toUpperCase() ?? "";
}

function displayNameFrom(
  name: string | null | undefined,
  email: string,
): string {
  const trimmedName = name?.trim();
  if (trimmedName) return trimmedName;
  return email.split("@")[0]?.trim() || email;
}

type UserIdentityBlockProps = {
  onOpenChange?: (open: boolean) => void;
};

export function UserIdentityBlock({ onOpenChange }: UserIdentityBlockProps) {
  const t = useTranslations("dashboard.userMenu");
  const router = useRouter();
  const authIdentity = useAuthStore((state) => state.authIdentity);
  const logout = useLogout();

  // The identity is client-only (hydrated from GET /v2/auth/me after mount), so
  // the server has no idea who's signed in. Render the neutral empty state on
  // the server and the first client paint alike — then reveal the real identity
  // once mounted — to avoid an SSR/hydration text mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  const identity = mounted ? authIdentity : null;

  const email = identity?.email ?? "";
  const displayName = displayNameFrom(identity?.name, email);
  const initials = initialsFrom(displayName, email);

  return (
    <DropdownMenu onOpenChange={onOpenChange}>
      <DropdownMenuTrigger
        className="-mx-1 flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition-colors hover:bg-ink-wash focus-visible:bg-ink-wash focus-visible:outline-none"
        aria-label={displayName || t("accountMenu")}
      >
        <Avatar size="lg">
          {identity?.avatar_url ? (
            <AvatarImage src={identity.avatar_url} alt={displayName} />
          ) : null}
          <AvatarFallback className="bg-brand-soft text-brand font-semibold">
            {initials}
          </AvatarFallback>
        </Avatar>
        <div className="flex min-w-0 flex-1 flex-col leading-tight">
          <span className="break-all text-md font-semibold text-ink-900 leading-snug">
            {displayName}
          </span>
          <span className="truncate text-xs text-ink-400">{email}</span>
        </div>
        <ChevronsUpDown className="size-5 shrink-0 text-ink-400" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        side="top"
        sideOffset={8}
        className="min-w-56"
      >
        <DropdownMenuItem asChild>
          <Link href="/dashboard/settings" className="cursor-pointer">
            <Settings className="size-4" aria-hidden />
            <span>{t("accountSettings")}</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a
            href="https://rpc.aurpay.net"
            target="_blank"
            rel="noreferrer"
            className="cursor-pointer"
          >
            <BookOpen className="size-4" aria-hidden />
            <span>{t("docs")}</span>
          </a>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={logout.isPending}
          onSelect={() => {
            logout.mutate(undefined, {
              onSuccess: () => router.replace("/login"),
            });
          }}
        >
          <LogOut className="size-4" aria-hidden />
          <span>{t("signOut")}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
