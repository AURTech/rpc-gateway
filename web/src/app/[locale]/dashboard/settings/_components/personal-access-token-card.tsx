"use client";

import { CopyIcon, KeyRoundIcon, PlusIcon, ShieldOffIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { isApiError } from "@/api/client";
import type {
  CreatedPersonalAccessToken,
  PersonalAccessToken,
  PersonalAccessTokenScope,
} from "@/api/personal-access-tokens/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Field } from "@/components/patterns/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Time } from "@/components/ui/time";
import {
  useCreatePersonalAccessToken,
  usePersonalAccessTokens,
  useRevokePersonalAccessToken,
} from "@/hooks/use-personal-access-tokens";
import { copyToClipboard } from "@/lib/clipboard";
import { useAuthStore } from "@/stores/auth-store";

const STANDARD_SCOPES: PersonalAccessTokenScope[] = [
  "overview:read",
  "apps:read",
  "apps:write",
  "app-keys:read",
  "app-keys:write",
  "gateways:read",
  "gateways:write",
  "endpoints:read",
  "endpoints:write",
  "endpoint-secrets:read",
  "providers:read",
  "providers:write",
  "provider-secrets:read",
  "routes:read",
  "routes:write",
  "usage:read",
  "meta:read",
];
const ADMIN_SCOPES: PersonalAccessTokenScope[] = [
  "accounts:read",
  "accounts:write",
  "policies:read",
  "policies:write",
];
const STATE_VARIANT = {
  active: "positive",
  expired: "neutral",
  revoked: "danger",
} as const;

function apiErrorMessage(error: unknown, fallback: string): string {
  return isApiError(error) && error.message ? error.message : fallback;
}

function expiryDate(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString();
}

export function PersonalAccessTokenCard() {
  const t = useTranslations("dashboard.settings.tokens");
  const identity = useAuthStore((state) => state.authIdentity);
  const query = usePersonalAccessTokens();
  const createMutation = useCreatePersonalAccessToken();
  const revokeMutation = useRevokePersonalAccessToken();
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [expiryDays, setExpiryDays] = useState("90");
  const [scopes, setScopes] = useState<Set<PersonalAccessTokenScope>>(
    new Set(["overview:read"]),
  );
  const [created, setCreated] = useState<CreatedPersonalAccessToken | null>(
    null,
  );
  const [revokeToken, setRevokeToken] = useState<PersonalAccessToken | null>(
    null,
  );

  const setScope = (scope: PersonalAccessTokenScope, checked: boolean) => {
    setScopes((selected) => {
      const next = new Set(selected);
      if (checked) next.add(scope);
      else next.delete(scope);
      return next;
    });
  };

  const closeCreate = () => {
    setCreateOpen(false);
    setCreated(null);
    setName("");
    setScopes(new Set(["overview:read"]));
    setExpiryDays("90");
  };

  const createToken = () => {
    if (!name.trim() || scopes.size === 0) return;
    createMutation.mutate(
      {
        name: name.trim(),
        scopes: [...scopes],
        expires_at: expiryDate(Number(expiryDays)),
      },
      {
        onSuccess: setCreated,
        onError: (error) =>
          toast.error(apiErrorMessage(error, t("errors.create"))),
      },
    );
  };

  const copyToken = async () => {
    if (!created) return;
    const copied = await copyToClipboard(created.token);
    toast[copied ? "success" : "error"](
      copied ? t("copied") : t("errors.copy"),
    );
  };

  const revoke = () => {
    if (!revokeToken) return;
    revokeMutation.mutate(revokeToken.id, {
      onSuccess: () => {
        toast.success(t("revoked"));
        setRevokeToken(null);
      },
      onError: (error) =>
        toast.error(apiErrorMessage(error, t("errors.revoke"))),
    });
  };

  const scopeOptions =
    identity?.identity_type === "admin"
      ? [...STANDARD_SCOPES, ...ADMIN_SCOPES]
      : STANDARD_SCOPES;
  const activeLimitReached =
    query.data !== undefined && query.data.active >= query.data.maxActive;

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="text-lg">{t("title")}</CardTitle>
            <p className="mt-1 text-sm text-ink-500">{t("description")}</p>
          </div>
          <Button
            type="button"
            onClick={() => setCreateOpen(true)}
            disabled={activeLimitReached}
          >
            <PlusIcon className="size-4" aria-hidden />
            {t("create")}
          </Button>
        </CardHeader>
        <CardContent>
          {query.data ? (
            <p className="mb-3 text-sm text-ink-500">
              {t("activeCount", {
                active: query.data.active,
                max: query.data.maxActive,
              })}
              {activeLimitReached ? ` ${t("limitReached")}` : null}
            </p>
          ) : null}
          {query.isPending ? (
            <p className="text-sm text-ink-500">{t("loading")}</p>
          ) : null}
          {query.isError ? (
            <div
              role="alert"
              className="rounded-lg bg-danger-soft p-4 text-sm text-danger"
            >
              {t("errors.load")}
            </div>
          ) : null}
          {query.data?.items.length === 0 ? (
            <p className="rounded-lg bg-ink-wash p-4 text-sm text-ink-500">
              {t("empty")}
            </p>
          ) : null}
          {query.data?.items.map((token) => (
            <div
              key={token.id}
              className="flex flex-wrap items-start justify-between gap-4 border-b border-ink-wash py-4 last:border-0"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-ink-900">{token.name}</span>
                  <Badge variant={STATE_VARIANT[token.state]} dot>
                    {t(`states.${token.state}`)}
                  </Badge>
                </div>
                <code className="mt-1 block text-xs text-ink-500">
                  {token.token_prefix}…
                </code>
                <p className="mt-2 text-xs text-ink-500">
                  {t("expires")} <Time value={token.expires_at} /> ·{" "}
                  {t("lastUsed")} <Time value={token.last_used_at} />
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {token.scopes.map((scope) => (
                    <Badge key={scope} variant="neutral">
                      {scope}
                    </Badge>
                  ))}
                </div>
              </div>
              {token.state === "active" ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setRevokeToken(token)}
                >
                  <ShieldOffIcon className="size-4" aria-hidden />
                  {t("revoke")}
                </Button>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>

      <Dialog
        open={createOpen}
        onOpenChange={(open) => (!open ? closeCreate() : setCreateOpen(true))}
      >
        <DialogContent className="max-h-screen overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {created ? t("secretTitle") : t("createTitle")}
            </DialogTitle>
            <DialogDescription>
              {created ? t("secretDescription") : t("createDescription")}
            </DialogDescription>
          </DialogHeader>
          {created ? (
            <div className="rounded-xl bg-warning-soft p-4">
              <code className="block break-all text-sm text-ink-900">
                {created.token}
              </code>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={copyToken}
              >
                <CopyIcon className="size-4" aria-hidden />
                {t("copy")}
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <Field label={t("name")} htmlFor="pat-name">
                <Input
                  id="pat-name"
                  maxLength={64}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field label={t("expiry")} htmlFor="pat-expiry">
                <Select value={expiryDays} onValueChange={setExpiryDays}>
                  <SelectTrigger id="pat-expiry" bordered>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[30, 90, 180, 365].map((days) => (
                      <SelectItem key={days} value={String(days)}>
                        {t("days", { days })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <fieldset>
                <legend className="text-sm font-medium text-ink-900">
                  {t("scopes")}
                </legend>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {scopeOptions.map((scope) => (
                    <label
                      key={scope}
                      htmlFor={`pat-scope-${scope.replace(":", "-")}`}
                      className="flex items-center gap-2 rounded-lg bg-ink-wash px-3 py-2 text-xs text-ink-700"
                    >
                      <Checkbox
                        id={`pat-scope-${scope.replace(":", "-")}`}
                        checked={scopes.has(scope)}
                        onCheckedChange={(checked) =>
                          setScope(scope, checked === true)
                        }
                      />
                      <code>{scope}</code>
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={closeCreate}>
              {created ? t("done") : t("cancel")}
            </Button>
            {!created ? (
              <Button
                type="button"
                onClick={createToken}
                disabled={
                  !name.trim() || scopes.size === 0 || createMutation.isPending
                }
              >
                <KeyRoundIcon className="size-4" aria-hidden />
                {createMutation.isPending ? t("creating") : t("create")}
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={revokeToken !== null}
        onOpenChange={(open) => !open && setRevokeToken(null)}
        title={t("revokeTitle")}
        description={t("revokeDescription", { name: revokeToken?.name ?? "" })}
        onConfirm={revoke}
        confirmLabel={t("revoke")}
        confirming={revokeMutation.isPending}
        confirmingLabel={t("revoking")}
        cancelLabel={t("cancel")}
      />
    </>
  );
}
