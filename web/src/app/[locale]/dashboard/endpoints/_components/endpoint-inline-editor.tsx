"use client";

import { Eye, EyeOff, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type { EndpointDetail } from "@/api/endpoints/client";
import { Field } from "@/components/patterns/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { Time } from "@/components/ui/time";
import { useUpdateEndpointMutation } from "@/hooks/use-endpoints";
import { EndpointUrlCopyButton } from "./copyable-endpoint-url";
import {
  buildEndpointUpdateInput,
  endpointFormFromDetail,
  endpointFormHasChanges,
  isEndpointHeaderValid,
  isEndpointVersionConflict,
  isValidEndpointUrl,
} from "./endpoint-form-model";

interface EndpointInlineEditorProps {
  endpoint: EndpointDetail;
  editing: boolean;
  onReload: () => Promise<EndpointDetail | null>;
  onFinishEditing: () => void;
}

export function EndpointInlineEditor({
  endpoint,
  editing,
  onReload,
  onFinishEditing,
}: EndpointInlineEditorProps) {
  const t = useTranslations("dashboard.endpoints");
  const [form, setForm] = useState(() => endpointFormFromDetail(endpoint));
  const [conflict, setConflict] = useState(false);
  const [showHeaderValue, setShowHeaderValue] = useState(false);
  const updateEndpoint = useUpdateEndpointMutation();
  const providerManaged = endpoint.origin_type === "provider";
  const dirty = endpointFormHasChanges(form, endpoint);
  const headerValid = isEndpointHeaderValid(form);
  const urlValid = providerManaged || isValidEndpointUrl(form.url);
  const valid = form.name.trim().length > 0 && headerValid && urlValid;
  const idBase = `endpoint-${endpoint.id}-inline`;

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((previous) => ({ ...previous, [key]: value }));

  const reset = () => {
    setForm(endpointFormFromDetail(endpoint));
    setConflict(false);
    setShowHeaderValue(false);
  };

  const reload = async () => {
    const latest = await onReload();
    if (latest) setForm(endpointFormFromDetail(latest));
    setConflict(false);
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!dirty || !valid || updateEndpoint.isPending) return;

    updateEndpoint.mutate(
      {
        id: endpoint.id,
        input: buildEndpointUpdateInput(form, endpoint),
      },
      {
        onSuccess: (updated) => {
          setForm(endpointFormFromDetail(updated));
          setConflict(false);
          onFinishEditing();
          toast.success(t("toast.updated"));
        },
        onError: (error) => {
          if (isEndpointVersionConflict(error)) setConflict(true);
          toast.error(
            isApiError(error) ? error.message : t("toast.updateError"),
          );
        },
      },
    );
  };

  const endpointUrl = endpoint.effective_url ?? endpoint.url;

  if (!editing) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <Fact label={t("fields.name")}>
          <span className="font-medium text-ink-900">{endpoint.name}</span>
        </Fact>

        <EndpointUrlSummary url={endpointUrl} />

        {providerManaged ? <ProviderFacts endpoint={endpoint} /> : null}

        <Fact label={t("rowExpansion.details.authentication")} mono>
          <EndpointAuthentication
            endpoint={endpoint}
            revealed={showHeaderValue}
            onToggle={() => setShowHeaderValue((value) => !value)}
          />
        </Fact>

        <MetadataFooter endpoint={endpoint} />
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="flex min-w-0 flex-col gap-6">
      {conflict ? (
        <div className="flex items-center justify-between gap-4 rounded-lg bg-warning-soft px-4 py-3 text-sm text-warning">
          <span>{t("form.conflict")}</span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={updateEndpoint.isPending}
            onClick={reload}
          >
            <RefreshCw aria-hidden />
            {t("form.reload")}
          </Button>
        </div>
      ) : null}

      <div className="grid grid-cols-12 gap-x-6 gap-y-5">
        <Field
          className="col-span-12"
          label={t("fields.name")}
          htmlFor={`${idBase}-name`}
          required
        >
          <Input
            id={`${idBase}-name`}
            autoFocus
            className="bg-stripe hover:bg-ink-wash focus:bg-surface"
            maxLength={128}
            value={form.name}
            onChange={(event) => set("name", event.target.value)}
          />
        </Field>

        {!providerManaged ? (
          <Field
            className="col-span-12"
            label={t("fields.url")}
            htmlFor={`${idBase}-url`}
            error={!urlValid ? t("fields.urlInvalid") : undefined}
            required
          >
            <InputGroup className="group/url bg-stripe hover:bg-ink-wash focus-within:bg-surface">
              <InputGroupInput
                id={`${idBase}-url`}
                maxLength={4096}
                mono
                value={form.url}
                onChange={(event) => set("url", event.target.value)}
                placeholder={t("fields.urlPlaceholder")}
                aria-invalid={!urlValid}
              />
              <InputGroupAddon>
                <EndpointUrlCopyButton
                  url={form.url}
                  className="opacity-0 transition-opacity group-hover/url:opacity-100 group-focus-within/url:opacity-100 focus-visible:opacity-100"
                />
              </InputGroupAddon>
            </InputGroup>
          </Field>
        ) : null}

        {!providerManaged ? (
          <>
            <Field
              className="col-span-6"
              label={t("fields.headerName")}
              htmlFor={`${idBase}-header-name`}
              error={
                form.headerValue.trim() && !form.headerName.trim()
                  ? t("fields.headerNameRequired")
                  : undefined
              }
            >
              <Input
                id={`${idBase}-header-name`}
                className="bg-stripe hover:bg-ink-wash focus:bg-surface"
                maxLength={128}
                mono
                value={form.headerName}
                onChange={(event) => set("headerName", event.target.value)}
                placeholder={t("fields.headerNamePlaceholder")}
                aria-invalid={Boolean(
                  form.headerValue.trim() && !form.headerName.trim(),
                )}
              />
            </Field>
            <Field
              className="col-span-6"
              label={t("fields.headerValue")}
              htmlFor={`${idBase}-header-value`}
              hint={t("fields.headerHint")}
              error={
                form.headerName.trim() && !form.headerValue.trim()
                  ? t("fields.headerValueRequired")
                  : undefined
              }
            >
              <InputGroup className="bg-stripe hover:bg-ink-wash focus-within:bg-surface">
                <InputGroupInput
                  id={`${idBase}-header-value`}
                  type={showHeaderValue ? "text" : "password"}
                  autoComplete="new-password"
                  maxLength={4096}
                  mono
                  value={form.headerValue}
                  onChange={(event) => set("headerValue", event.target.value)}
                  placeholder={t("fields.headerValuePlaceholder")}
                  aria-invalid={Boolean(
                    form.headerName.trim() && !form.headerValue.trim(),
                  )}
                />
                <InputGroupAddon>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={
                      showHeaderValue
                        ? t("fields.hideHeaderValue")
                        : t("fields.showHeaderValue")
                    }
                    aria-pressed={showHeaderValue}
                    onClick={() => setShowHeaderValue((value) => !value)}
                  >
                    {showHeaderValue ? (
                      <EyeOff aria-hidden />
                    ) : (
                      <Eye aria-hidden />
                    )}
                  </Button>
                </InputGroupAddon>
              </InputGroup>
            </Field>
          </>
        ) : null}
      </div>

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={updateEndpoint.isPending}
          onClick={() => {
            reset();
            onFinishEditing();
          }}
        >
          {t("cancel")}
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={!dirty || !valid || updateEndpoint.isPending}
        >
          {updateEndpoint.isPending ? t("saving") : t("save")}
        </Button>
      </div>
    </form>
  );
}

function EndpointUrlSummary({ url }: { url: string }) {
  const t = useTranslations("dashboard.endpoints");

  return (
    <section aria-label={t("rowExpansion.details.endpointUrl")}>
      <div className="text-sm font-medium text-ink-500">
        {t("rowExpansion.details.endpointUrl")}
      </div>
      <div className="mt-2 flex min-w-0 items-start gap-2">
        <code className="min-w-0 break-all font-mono text-md font-medium leading-6 text-ink-900">
          {url}
        </code>
        <EndpointUrlCopyButton url={url} className="mt-0.5 shrink-0" />
      </div>
    </section>
  );
}

function ProviderFacts({ endpoint }: { endpoint: EndpointDetail }) {
  const t = useTranslations("dashboard.endpoints");
  const syncStatus = endpoint.provider_sync_status;

  return (
    <div className="grid grid-cols-12 gap-x-8 gap-y-4">
      <Fact className="col-span-4" label={t("fields.provider")}>
        {endpoint.provider ? (
          <span className="flex min-w-0 flex-col">
            <span className="truncate font-medium text-ink-700">
              {endpoint.provider.name}
            </span>
            <span className="truncate text-xs text-ink-500">
              {endpoint.provider.vendor_label}
            </span>
          </span>
        ) : (
          <span className="font-medium text-warning">
            {t("rowExpansion.provider.unavailableTitle")}
          </span>
        )}
      </Fact>
      <Fact
        className="col-span-3"
        label={t("rowExpansion.provider.externalId")}
        mono
      >
        {endpoint.provider_external_id ?? "—"}
      </Fact>
      <Fact
        className="col-span-2"
        label={t("rowExpansion.provider.syncStatus")}
      >
        {syncStatus ? (
          <span
            className={`font-medium ${syncStatus === "available" ? "text-positive" : "text-warning"}`}
          >
            {t(`rowExpansion.provider.status.${syncStatus}`)}
          </span>
        ) : (
          "—"
        )}
      </Fact>
      <Fact className="col-span-3" label={t("rowExpansion.provider.lastSeen")}>
        <Time value={endpoint.provider_last_seen_at} />
      </Fact>
    </div>
  );
}

function EndpointAuthentication({
  endpoint,
  revealed,
  onToggle,
}: {
  endpoint: EndpointDetail;
  revealed: boolean;
  onToggle: () => void;
}) {
  const t = useTranslations("dashboard.endpoints");

  if (endpoint.auth.type === "none") return t("rowExpansion.details.noAuth");
  if (
    endpoint.auth.type === "query_api_key" ||
    endpoint.auth.type === "path_api_key"
  ) {
    return t("rowExpansion.details.authInUrl");
  }

  const name =
    endpoint.auth.type === "bearer"
      ? "Authorization"
      : endpoint.auth.header_name;
  const secret = "secret" in endpoint.auth ? endpoint.auth.secret : null;
  const value =
    endpoint.auth.type === "bearer"
      ? `Bearer ${revealed && secret ? secret : "••••••••••••"}`
      : revealed && secret
        ? secret
        : "••••••••••••";

  return (
    <span className="inline-flex max-w-full items-center gap-1.5 text-ink-700">
      <span className="break-all">
        {name}: {value}
      </span>
      {secret ? (
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          className="shrink-0 text-ink-500"
          aria-label={
            revealed
              ? t("rowExpansion.details.hideAuth")
              : t("rowExpansion.details.showAuth")
          }
          aria-pressed={revealed}
          onClick={onToggle}
        >
          {revealed ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
        </Button>
      ) : null}
    </span>
  );
}

function Fact({
  className,
  label,
  mono = false,
  children,
}: {
  className?: string;
  label: string;
  mono?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <div className="text-xs font-medium text-ink-400">{label}</div>
      <div
        className={`mt-1 min-w-0 text-sm text-ink-700 ${mono ? "font-mono" : ""}`}
      >
        {children}
      </div>
    </div>
  );
}

function MetadataFooter({ endpoint }: { endpoint: EndpointDetail }) {
  const t = useTranslations("dashboard.endpoints");

  return (
    <footer className="border-t border-table-frame pt-4">
      <dl className="flex min-w-0 flex-wrap items-center gap-x-7 gap-y-2 text-xs text-ink-400">
        <div className="flex min-w-0 items-center gap-2">
          <dt>{t("rowExpansion.details.id")}</dt>
          <dd
            className="max-w-64 truncate font-mono tabular-nums text-ink-500"
            title={endpoint.id}
          >
            {endpoint.id}
          </dd>
        </div>
        <div className="flex items-center gap-2">
          <dt>{t("rowExpansion.details.created")}</dt>
          <dd className="text-ink-500">
            <Time value={endpoint.created_at} />
          </dd>
        </div>
        <div className="flex items-center gap-2">
          <dt>{t("rowExpansion.details.version")}</dt>
          <dd className="font-mono tabular-nums text-ink-500">
            v{endpoint.version}
          </dd>
        </div>
      </dl>
    </footer>
  );
}
