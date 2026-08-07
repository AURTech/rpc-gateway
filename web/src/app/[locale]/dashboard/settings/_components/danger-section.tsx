"use client";

import { LogOut } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useLogout } from "@/hooks/use-auth";
import { useRouter } from "@/i18n/navigation";

export function DangerSection() {
  const t = useTranslations("dashboard.settings.danger");
  const logout = useLogout();
  const router = useRouter();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button
          variant="destructive"
          disabled={logout.isPending}
          onClick={() =>
            logout.mutate(undefined, {
              onSuccess: () => router.replace("/login"),
            })
          }
        >
          <LogOut className="size-4" aria-hidden />
          {logout.isPending ? t("signing_out") : t("sign_out")}
        </Button>
      </CardContent>
    </Card>
  );
}
