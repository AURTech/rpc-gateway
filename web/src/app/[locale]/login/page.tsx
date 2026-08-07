"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useState } from "react";
import { getGoogleLoginUrl } from "@/api/auth/actions";
import { passwordLogin } from "@/api/auth/client";
import { isApiError } from "@/api/client";
import { AuthShell } from "@/components/patterns/auth-shell";
import { Field } from "@/components/patterns/form-field";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { authIdentityQueryKey } from "@/hooks/use-auth";
import { Link, useRouter } from "@/i18n/navigation";
import { authErrorKey } from "@/lib/auth-error";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label="Google" focusable="false">
      <title>Google</title>
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.79-.07-1.54-.2-2.27H12v4.51h6.47a5.53 5.53 0 0 1-2.4 3.63v3h3.88c2.27-2.09 3.57-5.17 3.57-8.87Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.08 7.95-2.91l-3.88-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.27v3.09A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.29a7.21 7.21 0 0 1 0-4.58V6.62H1.27a12 12 0 0 0 0 10.76l4-3.09Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.43-3.43A11.97 11.97 0 0 0 12 0 12 12 0 0 0 1.27 6.62l4 3.09C6.22 6.86 8.87 4.75 12 4.75Z"
      />
    </svg>
  );
}

function LoginContent() {
  const t = useTranslations("auth");
  const reduce = useReducedMotion();
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const errorKey = authErrorKey(searchParams.get("error"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const login = useMutation({
    mutationFn: passwordLogin,
    meta: { skipGlobalErrorToast: true },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: authIdentityQueryKey });
      router.replace("/dashboard");
    },
  });

  const canSubmit =
    email.trim().length > 0 && password.length > 0 && !login.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    login.mutate({ email: email.trim(), password });
  };

  const loginErrorMessage = login.isError
    ? isApiError(login.error) && login.error.status === 401
      ? t("password_error_invalid")
      : t("password_error_unknown")
    : null;

  // Auth failures (e.g. 401) are an email-or-password problem, not a
  // field-level validation error, so they surface as a form-level alert.
  // A live login error takes precedence over a stale URL `error` param.
  const formErrorMessage = loginErrorMessage ?? (errorKey ? t(errorKey) : null);

  return (
    <AuthShell footnote={t("footnote")}>
      <Card className="w-full gap-6 px-6">
        <div className="flex flex-col gap-1.5 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-ink-900">
            {t("signin_title")}
          </h1>
          <p className="text-md text-ink-500">{t("signin_subtitle")}</p>
        </div>

        {/* Alert + form share a gap-less column so the error's reveal is a
            single height animation: the form is pushed down smoothly instead
            of jumping. The alert owns its own bottom spacing (mb-6) inside the
            collapsing wrapper, matching the card's gap-6 rhythm when open. */}
        <div className="flex w-full flex-col">
          <AnimatePresence initial={false}>
            {formErrorMessage ? (
              <motion.div
                key="login-error"
                className="overflow-hidden"
                initial={reduce ? false : { height: 0, opacity: 0 }}
                animate={
                  reduce ? { opacity: 1 } : { height: "auto", opacity: 1 }
                }
                exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              >
                <div
                  role="alert"
                  className="mb-6 flex w-full items-start gap-2 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger"
                >
                  <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <span>{formErrorMessage}</span>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>

          <form className="flex w-full flex-col gap-4" onSubmit={handleSubmit}>
            <Field label={t("email_label")} htmlFor="login-email">
              <Input
                id="login-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("email_placeholder")}
                disabled={login.isPending}
              />
            </Field>
            <Field label={t("password_label")} htmlFor="login-password">
              <div className="relative">
                <Input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t("password_placeholder")}
                  disabled={login.isPending}
                  className="pr-10"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="absolute top-1/2 right-1 -translate-y-1/2 text-ink-400 before:absolute before:-inset-1.5 before:content-[''] hover:text-ink-700"
                  aria-label={
                    showPassword ? t("hide_password") : t("show_password")
                  }
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((value) => !value)}
                  disabled={login.isPending}
                >
                  {showPassword ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
                </Button>
              </div>
            </Field>
            <Button
              type="submit"
              size="lg"
              className="w-full"
              disabled={!canSubmit}
            >
              {login.isPending ? (
                <>
                  <Loader2 className="animate-spin" aria-hidden />
                  {t("signing_in")}
                </>
              ) : (
                t("sign_in")
              )}
            </Button>
          </form>
        </div>

        <div className="flex w-full items-center gap-3">
          <span className="h-px flex-1 bg-ink-wash" />
          <span className="text-sm text-ink-400">{t("divider")}</span>
          <span className="h-px flex-1 bg-ink-wash" />
        </div>

        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full"
          aria-label={t("continue_with_google_aria")}
          onClick={() => {
            window.location.href = getGoogleLoginUrl();
          }}
        >
          <GoogleIcon />
          {t("continue_with_google")}
        </Button>

        <p className="text-center text-sm text-ink-400">
          {t("policy_line")}{" "}
          <Link href="/terms" className="text-brand hover:underline">
            {t("tos_link")}
          </Link>{" "}
          {t("policy_separator")}{" "}
          <Link href="/privacy" className="text-brand hover:underline">
            {t("privacy_link")}
          </Link>
          {t("policy_suffix")}
        </p>
      </Card>
    </AuthShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginContent />
    </Suspense>
  );
}
