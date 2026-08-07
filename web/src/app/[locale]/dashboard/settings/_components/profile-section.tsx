"use client";

import { useTranslations } from "next-intl";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthIdentity } from "@/hooks/use-auth";

/** Up to two initials from a display name, falling back to the email. */
function initialsFrom(name: string | null | undefined, email: string): string {
  const source = name?.trim() || email;
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-sm text-ink-500">{label}</dt>
      <dd className="min-w-0 truncate text-md text-ink-900">{children}</dd>
    </div>
  );
}

export function ProfileSection() {
  const t = useTranslations("dashboard.settings.profile");
  const { data, isPending } = useAuthIdentity();

  const name = data?.name?.trim() || data?.email || "";
  const email = data?.email ?? "";
  const isAdmin = data?.identity_type === "admin";

  return (
    <Card>
      <CardContent className="flex flex-col gap-6">
        {isPending ? (
          <div className="flex items-center gap-4">
            <Skeleton className="size-10 rounded-full" />
            <div className="flex flex-col gap-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-4">
            <Avatar size="lg">
              {data?.avatar_url ? (
                <AvatarImage src={data.avatar_url} alt={name} />
              ) : null}
              <AvatarFallback className="bg-brand-soft text-brand font-semibold">
                {initialsFrom(data?.name, email)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <div className="truncate text-md font-semibold text-ink-900">
                {name}
              </div>
              <div className="truncate text-sm text-ink-400">{email}</div>
            </div>
          </div>
        )}

        <dl className="flex flex-col gap-4">
          <Row label={t("name")}>
            {isPending ? (
              <Skeleton className="h-4 w-24" />
            ) : (
              (data?.name?.trim() ?? "—")
            )}
          </Row>
          <Row label={t("email")}>
            {isPending ? <Skeleton className="h-4 w-40" /> : email}
          </Row>
          <Row label={t("role")}>
            {isPending ? (
              <Skeleton className="h-5 w-16" />
            ) : (
              <Badge variant={isAdmin ? "brand" : "neutral"}>
                {isAdmin ? t("role_admin") : t("role_user")}
              </Badge>
            )}
          </Row>
        </dl>
      </CardContent>
    </Card>
  );
}
