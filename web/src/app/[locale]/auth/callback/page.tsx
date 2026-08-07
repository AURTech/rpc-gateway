"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useEffect } from "react";

import { AuthShell } from "@/components/patterns/auth-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { authIdentityQueryKey, useAuthIdentity } from "@/hooks/use-auth";
import { Link, useRouter } from "@/i18n/navigation";

function AuthCallbackContent() {
  const t = useTranslations("auth");
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const oauthError = searchParams.get("error");

  // The backend has just set (or failed to set) the session cookie. Drop any
  // stale cached result so we re-verify against /v2/auth/me.
  useEffect(() => {
    if (!oauthError) {
      queryClient.invalidateQueries({ queryKey: authIdentityQueryKey });
    }
  }, [oauthError, queryClient]);

  const { data, isError } = useAuthIdentity({ enabled: !oauthError });

  useEffect(() => {
    if (data) {
      router.replace("/dashboard");
    }
  }, [data, router]);

  const failed = Boolean(oauthError) || isError;

  if (failed) {
    return (
      <AuthShell>
        <Card className="w-full items-center gap-6 px-6 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-danger-soft text-danger">
            <AlertCircle className="size-6" aria-hidden />
          </span>
          <div className="flex flex-col gap-1.5">
            <h1 className="text-2xl font-bold tracking-tight text-ink-900">
              {t("callback_error_title")}
            </h1>
            <p className="text-md text-ink-500">
              {t("callback_error_subtitle")}
            </p>
          </div>
          <Button asChild variant="outline" size="lg" className="w-full">
            <Link href="/login">{t("back_to_signin")}</Link>
          </Button>
        </Card>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <Card className="w-full items-center gap-4 px-6 text-center">
        <Loader2 className="size-8 animate-spin text-brand" aria-hidden />
        <div className="flex flex-col gap-1.5">
          <h1 className="text-2xl font-bold tracking-tight text-ink-900">
            {t("callback_pending_title")}
          </h1>
          <p className="text-md text-ink-500">
            {t("callback_pending_subtitle")}
          </p>
        </div>
      </Card>
    </AuthShell>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={null}>
      <AuthCallbackContent />
    </Suspense>
  );
}
