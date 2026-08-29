"use client";

import {
  CopyIcon,
  EllipsisIcon,
  KeyRoundIcon,
  ShieldOffIcon,
} from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
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
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableRow,
} from "@/components/ui/table";
import {
  useCreatePersonalAccessToken,
  usePersonalAccessTokens,
  useRevokePersonalAccessToken,
} from "@/hooks/use-personal-access-tokens";
import { copyToClipboard } from "@/lib/clipboard";
import { formatAbsoluteFull } from "@/lib/format-time";
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
function expiresWithinDays(
  token: PersonalAccessToken,
  days: number,
  now: number,
): boolean {
  if (token.state !== "active") return false;
  const expiresAt = Date.parse(token.expires_at);
  return expiresAt >= now && expiresAt <= now + days * 86_400_000;
}

function apiErrorMessage(error: unknown, fallback: string): string {
  return isApiError(error) && error.message ? error.message : fallback;
}

function expiryDate(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString();
}

export function PersonalAccessTokenCard() {
  const t = useTranslations("dashboard.settings.tokens");
  const locale = useLocale();
  const dateFormatter = new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
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

  const renderDate = (value: string | null, fallback = "—") => {
    if (!value) return <span>{fallback}</span>;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return <span>{value}</span>;
    return (
      <time
        dateTime={date.toISOString()}
        title={formatAbsoluteFull(value) ?? undefined}
        className="font-medium text-ink-700 tabular-nums"
      >
        {dateFormatter.format(date)}
      </time>
    );
  };

  const scopeOptions =
    identity?.identity_type === "admin"
      ? [...STANDARD_SCOPES, ...ADMIN_SCOPES]
      : STANDARD_SCOPES;
  const activeLimitReached =
    query.data !== undefined && query.data.active >= query.data.maxActive;
  const tokens = query.data?.items ?? [];
  const now = Date.now();
  const expiringCount = tokens.filter((token) =>
    expiresWithinDays(token, 14, now),
  ).length;
  const unusedCount = tokens.filter(
    (token) => token.last_used_at === null,
  ).length;
  const summaryItems: Array<{
    key: "active" | "expiring" | "unused" | "usage";
    value: number | string;
  }> = [
    { key: "active", value: query.data?.active ?? 0 },
    { key: "expiring", value: expiringCount },
    { key: "unused", value: unusedCount },
    {
      key: "usage",
      value: query.data
        ? `${query.data.active} / ${query.data.maxActive}`
        : "—",
    },
  ];

  return (
    <>
      <div className="flex flex-col gap-6">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {summaryItems.map((item) => (
            <div
              key={item.key}
              className="flex flex-col rounded-xl bg-table-frame p-1"
            >
              <span className="block px-3 py-2 text-sm font-semibold text-ink-700">
                {t(`summary.${item.key}`)}
              </span>
              <div className="flex flex-1 flex-col rounded-lg bg-surface p-4">
                <strong className="block text-3xl font-semibold text-ink-900 tabular-nums">
                  {query.data ? item.value : "—"}
                </strong>
                <span className="mt-2 text-xs text-ink-500">
                  {t(`summaryHints.${item.key}`)}
                </span>
              </div>
            </div>
          ))}
        </div>

        <section
          data-slot="personal-access-tokens"
          className="overflow-hidden rounded-3xl bg-table-frame"
        >
          <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
            <div className="min-w-0 flex-1 basis-52">
              <h2 className="text-sm font-semibold text-ink-900">
                {t("title")}
              </h2>
              <p className="mt-0.5 text-2xs leading-snug text-ink-500">
                {t("description")}
              </p>
            </div>
            <Button
              type="button"
              variant="soft"
              size="sm"
              className="shrink-0 rounded-xl"
              onClick={() => setCreateOpen(true)}
              disabled={activeLimitReached}
            >
              {t("generate")}
            </Button>
          </header>

          <div className="mx-1 mb-1 rounded-table-pill bg-surface p-4">
            <Table
              compact
              dividers
              frameless
              aria-label={t("title")}
              className="table-fixed"
              scrollClassName="overflow-x-hidden"
            >
              <TableCaption>{t("title")}</TableCaption>
              <TableBody>
                {query.isPending ? (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="h-28 text-center text-ink-500"
                    >
                      {t("loading")}
                    </TableCell>
                  </TableRow>
                ) : null}
                {query.isError ? (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="h-28 text-center text-danger"
                    >
                      <span role="alert">{t("errors.load")}</span>
                    </TableCell>
                  </TableRow>
                ) : null}
                {query.data && tokens.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="h-28 text-center text-ink-500"
                    >
                      {t("empty")}
                    </TableCell>
                  </TableRow>
                ) : null}
                {tokens.map((token) => {
                  const visibleScopes = token.scopes.slice(0, 2);
                  const hiddenScopeCount =
                    token.scopes.length - visibleScopes.length;
                  const compactVisibleScopes = token.scopes.slice(0, 1);
                  const compactHiddenScopeCount =
                    token.scopes.length - compactVisibleScopes.length;

                  return (
                    <TableRow key={token.id}>
                      <TableCell className="min-w-0 overflow-hidden py-4 align-top lg:w-1/3">
                        <div className="min-w-0">
                          <div className="flex min-w-0 items-center gap-2">
                            <p
                              className="min-w-0 truncate text-sm font-semibold text-ink-900"
                              title={token.name}
                            >
                              {token.name}
                            </p>
                            <Badge
                              variant={STATE_VARIANT[token.state]}
                              className="shrink-0 sm:hidden"
                            >
                              {t(`states.${token.state}`)}
                            </Badge>
                          </div>
                          <code className="mt-1 block truncate whitespace-nowrap font-mono text-xs leading-5 text-ink-500">
                            {token.token_prefix}…
                          </code>
                          <div className="mt-3 flex flex-col gap-2 lg:hidden">
                            <div
                              className="flex min-w-0 flex-wrap gap-1"
                              title={token.scopes.join(", ")}
                            >
                              {compactVisibleScopes.map((scope) => (
                                <Badge
                                  key={scope}
                                  variant="neutral"
                                  className="text-ink-700"
                                >
                                  {scope}
                                </Badge>
                              ))}
                              {compactHiddenScopeCount > 0 ? (
                                <Badge
                                  variant="neutral"
                                  className="text-ink-700"
                                >
                                  {t("moreScopes", {
                                    count: compactHiddenScopeCount,
                                  })}
                                </Badge>
                              ) : null}
                            </div>
                            <div className="grid gap-1.5 text-xs sm:grid-cols-2 sm:gap-3">
                              <p className="min-w-0 truncate text-ink-500">
                                {t("expires")} {renderDate(token.expires_at)}
                              </p>
                              <p className="min-w-0 truncate text-ink-500">
                                {token.last_used_at
                                  ? `${t("lastUsed")} `
                                  : null}
                                {renderDate(token.last_used_at, t("neverUsed"))}
                              </p>
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="hidden w-24 py-4 align-top sm:table-cell">
                        <Badge variant={STATE_VARIANT[token.state]}>
                          {t(`states.${token.state}`)}
                        </Badge>
                      </TableCell>
                      <TableCell className="hidden py-4 align-top lg:table-cell lg:w-1/4">
                        <div
                          className="flex flex-wrap gap-1"
                          title={token.scopes.join(", ")}
                        >
                          {visibleScopes.map((scope) => (
                            <Badge
                              key={scope}
                              variant="neutral"
                              className="text-ink-700"
                            >
                              {scope}
                            </Badge>
                          ))}
                          {hiddenScopeCount > 0 ? (
                            <Badge variant="neutral" className="text-ink-700">
                              {t("moreScopes", { count: hiddenScopeCount })}
                            </Badge>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="hidden py-4 align-top lg:table-cell lg:w-1/4">
                        <div className="flex flex-col gap-1.5 text-xs">
                          <p className="whitespace-nowrap text-ink-500">
                            {t("expires")} {renderDate(token.expires_at)}
                          </p>
                          <p className="whitespace-nowrap text-ink-500">
                            {token.last_used_at ? `${t("lastUsed")} ` : null}
                            {renderDate(token.last_used_at, t("neverUsed"))}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell align="right" className="w-14 py-3 align-top">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              aria-label={t("actions.open", {
                                name: token.name,
                              })}
                            >
                              <EllipsisIcon className="size-4" aria-hidden />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {token.state === "active" ? (
                              <DropdownMenuItem
                                variant="destructive"
                                onSelect={() => setRevokeToken(token)}
                              >
                                <ShieldOffIcon className="size-4" aria-hidden />
                                {t("revoke")}
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem disabled>
                                {t("noAction")}
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </section>
      </div>

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
            <div className="rounded-xl bg-ink-wash p-4">
              <code className="block break-all font-mono text-sm leading-6 text-ink-900">
                {created.token}
              </code>
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
            {created ? (
              <Button type="button" onClick={copyToken}>
                <CopyIcon className="size-4" aria-hidden />
                {t("copy")}
              </Button>
            ) : (
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
            )}
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
