"use client";

import { Eye, EyeOff, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import {
  type CreateEndpointInput,
  ENDPOINT_PROTOCOLS,
  type Endpoint,
  type EndpointProtocol,
} from "@/api/endpoints/client";
import {
  ALL_CHAIN_NETWORK_PAIRS,
  ChainNetworkSelect,
} from "@/components/patterns/chain-network-select";
import { Field } from "@/components/patterns/form-field";
import { Button } from "@/components/ui/button";
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
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sheet, SheetShell } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import {
  useCreateEndpointMutation,
  useEndpointQuery,
  useUpdateEndpointMutation,
} from "@/hooks/use-endpoints";
import type { Chain, Network } from "@/lib/blockchain";
import {
  buildEndpointUpdateInput,
  EMPTY_ENDPOINT_FORM,
  type EndpointFormState,
  endpointFormFromDetail,
  isEndpointHeaderValid,
  isEndpointVersionConflict,
  isValidEndpointUrl,
  makeEndpointCreateAuth,
} from "./endpoint-form-model";

const FORM_ID = "endpoint-form";

/** Lightweight form section: an uppercase eyebrow heading over a stacked group
 *  of fields. File-local — matches the detail sheet's section-label token. */
/** Field grouping wrapper. The form no longer shows section headings, so this
 *  is purely a flex column that keeps a uniform gap between its fields; the
 *  form's own gap keeps that same rhythm across group boundaries. */
function FormSection({ children }: { children: React.ReactNode }) {
  return <section className="flex flex-col gap-4">{children}</section>;
}

/** Standalone enabled toggle row: label (+ hint) left, switch right, separated
 *  from the sections above by a hairline. */
function EnabledRow({
  label,
  hint,
  checked,
  onCheckedChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-t border-ink-wash pt-5">
      <div className="min-w-0">
        <div className="text-md font-medium text-ink-900">{label}</div>
        {hint ? <p className="mt-0.5 text-sm text-ink-500">{hint}</p> : null}
      </div>
      <Switch
        id="endpoint-enabled"
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-label={label}
      />
    </div>
  );
}

/**
 * Shared create + edit form for endpoints. It supports centered dialogs and
 * right-side sheets. On edit it fetches the full record, maps legacy auth
 * configurations into a URL plus optional request header, sends only changed
 * fields, and surfaces optimistic-concurrency conflicts via `expected_version`.
 */
export function EditEndpointSheet({
  endpoint,
  initialChain,
  initialNetwork,
  initialProtocol,
  open,
  onOpenChange,
  presentation = "sheet",
}: {
  endpoint?: Endpoint | null;
  initialChain?: Chain;
  initialNetwork?: Network;
  initialProtocol?: EndpointProtocol;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  presentation?: "dialog" | "sheet";
}) {
  const t = useTranslations("dashboard.endpoints");
  const detailQuery = useEndpointQuery(open && endpoint ? endpoint.id : null);
  const detail = detailQuery.data ?? null;
  const [form, setForm] = useState<EndpointFormState>(EMPTY_ENDPOINT_FORM);
  const [conflict, setConflict] = useState(false);
  const [showHeaderValue, setShowHeaderValue] = useState(false);
  const createMutation = useCreateEndpointMutation();
  const updateMutation = useUpdateEndpointMutation();
  const editing = endpoint !== undefined && endpoint !== null;
  const providerManaged = (detail ?? endpoint)?.origin_type === "provider";

  useEffect(() => {
    if (!open) return;
    if (editing) {
      setForm(detail ? endpointFormFromDetail(detail) : EMPTY_ENDPOINT_FORM);
    } else {
      setForm({
        ...EMPTY_ENDPOINT_FORM,
        chain: initialChain ?? EMPTY_ENDPOINT_FORM.chain,
        network: initialNetwork ?? EMPTY_ENDPOINT_FORM.network,
        protocol: initialProtocol ?? EMPTY_ENDPOINT_FORM.protocol,
      });
    }
    setConflict(false);
    setShowHeaderValue(false);
  }, [detail, editing, initialChain, initialNetwork, initialProtocol, open]);

  const valid =
    (!editing || detail !== null) &&
    form.name.trim().length > 0 &&
    (providerManaged || isValidEndpointUrl(form.url)) &&
    (providerManaged || isEndpointHeaderValid(form));
  const busy = createMutation.isPending || updateMutation.isPending;

  const set = <K extends keyof EndpointFormState>(
    key: K,
    value: EndpointFormState[K],
  ) => setForm((previous) => ({ ...previous, [key]: value }));

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!valid || busy) return;
    if (!detail) {
      const input: CreateEndpointInput = {
        name: form.name.trim(),
        chain: form.chain,
        network: form.network,
        protocol: form.protocol,
        url: form.url.trim(),
        enabled: form.enabled,
        auth: makeEndpointCreateAuth(form),
      };
      createMutation.mutate(input, {
        onSuccess: () => {
          toast.success(t("toast.created"));
          onOpenChange(false);
        },
        onError: (error) =>
          toast.error(
            isApiError(error) ? error.message : t("toast.createError"),
          ),
      });
      return;
    }

    const input = buildEndpointUpdateInput(form, detail);
    input.name = form.name.trim();
    input.enabled = form.enabled;
    updateMutation.mutate(
      { id: detail.id, input },
      {
        onSuccess: () => {
          toast.success(t("toast.updated"));
          onOpenChange(false);
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

  const reload = async () => {
    const result = await detailQuery.refetch();
    if (result.data) setForm(endpointFormFromDetail(result.data));
    setConflict(false);
  };

  const handleOpenChange = (next: boolean) => {
    if (busy) return;
    onOpenChange(next);
  };

  const footer = (
    <div className="flex items-center justify-end gap-2">
      <Button
        type="button"
        variant="outline"
        disabled={busy}
        onClick={() => handleOpenChange(false)}
      >
        {t("cancel")}
      </Button>
      <Button type="submit" form={FORM_ID} disabled={!valid || busy}>
        {busy ? t("saving") : editing ? t("save") : t("create")}
      </Button>
    </div>
  );

  const title = editing ? t("form.editTitle") : t("form.createTitle");
  const description = editing
    ? t("form.editDescription")
    : t("form.createDescription");
  return (
    <EndpointOverlayRoot
      presentation={presentation}
      open={open}
      onOpenChange={handleOpenChange}
    >
      <EndpointOverlayShell
        presentation={presentation}
        title={title}
        description={description}
        closeLabel={t("cancel")}
        footer={footer}
      >
        <div className="flex flex-col gap-6">
          {conflict ? (
            <div className="flex items-center justify-between gap-3 rounded-lg bg-warning-soft p-3 text-sm text-warning">
              <span>{t("form.conflict")}</span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={reload}
              >
                <RefreshCw aria-hidden />
                {t("form.reload")}
              </Button>
            </div>
          ) : null}
          <form id={FORM_ID} onSubmit={submit} className="flex flex-col gap-4">
            <FormSection>
              <Field label={t("fields.name")} htmlFor="endpoint-name" required>
                <Input
                  id="endpoint-name"
                  maxLength={128}
                  value={form.name}
                  onChange={(event) => set("name", event.target.value)}
                />
              </Field>
              <Field
                label={t("fields.protocol")}
                htmlFor="endpoint-protocol"
                required
              >
                <Select
                  value={form.protocol}
                  onValueChange={(value) =>
                    set("protocol", value as EndpointProtocol)
                  }
                  disabled={editing}
                >
                  <SelectTrigger
                    id="endpoint-protocol"
                    aria-label={t("fields.protocol")}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ENDPOINT_PROTOCOLS.map((protocol) => (
                      <SelectItem key={protocol} value={protocol}>
                        {t(`protocol.${protocol}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field
                label={t("fields.chainNetwork")}
                htmlFor="endpoint-chain-network"
                required
              >
                <ChainNetworkSelect
                  inputId="endpoint-chain-network"
                  options={ALL_CHAIN_NETWORK_PAIRS}
                  value={{ chain: form.chain, network: form.network }}
                  onChange={({ chain, network }) => {
                    setForm((prev) => ({ ...prev, chain, network }));
                  }}
                  disabled={editing}
                />
              </Field>
            </FormSection>

            {providerManaged ? null : (
              <FormSection>
                <Field
                  label={t("fields.url")}
                  htmlFor="endpoint-url"
                  required={!editing}
                >
                  <Input
                    id="endpoint-url"
                    maxLength={4096}
                    mono
                    value={form.url}
                    onChange={(event) => set("url", event.target.value)}
                    placeholder={t("fields.urlPlaceholder")}
                  />
                </Field>
              </FormSection>
            )}

            {providerManaged ? null : (
              <FormSection>
                <Field
                  label={t("fields.headerName")}
                  htmlFor="endpoint-header-name"
                  error={
                    form.headerValue.trim() && !form.headerName.trim()
                      ? t("fields.headerNameRequired")
                      : undefined
                  }
                >
                  <Input
                    id="endpoint-header-name"
                    maxLength={128}
                    mono
                    value={form.headerName}
                    onChange={(event) => set("headerName", event.target.value)}
                    placeholder={t("fields.headerNamePlaceholder")}
                  />
                </Field>
                <Field
                  label={t("fields.headerValue")}
                  htmlFor="endpoint-header-value"
                  hint={t("fields.headerHint")}
                  error={
                    form.headerName.trim() && !form.headerValue.trim()
                      ? t("fields.headerValueRequired")
                      : undefined
                  }
                >
                  <InputGroup>
                    <InputGroupInput
                      id="endpoint-header-value"
                      type={showHeaderValue ? "text" : "password"}
                      autoComplete="new-password"
                      maxLength={4096}
                      mono
                      value={form.headerValue}
                      onChange={(event) =>
                        set("headerValue", event.target.value)
                      }
                      placeholder={t("fields.headerValuePlaceholder")}
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
              </FormSection>
            )}

            <EnabledRow
              label={t("fields.enabled")}
              hint={t("fields.enabledHint")}
              checked={form.enabled}
              onCheckedChange={(value) => set("enabled", value)}
            />
          </form>
        </div>
      </EndpointOverlayShell>
    </EndpointOverlayRoot>
  );
}

function EndpointOverlayRoot({
  presentation,
  open,
  onOpenChange,
  children,
}: {
  presentation: "dialog" | "sheet";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  return presentation === "dialog" ? (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {children}
    </Dialog>
  ) : (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {children}
    </Sheet>
  );
}

function EndpointOverlayShell({
  presentation,
  title,
  description,
  closeLabel,
  footer,
  children,
}: {
  presentation: "dialog" | "sheet";
  title: ReactNode;
  description: ReactNode;
  closeLabel: string;
  footer: ReactNode;
  children: ReactNode;
}) {
  if (presentation === "dialog") {
    return (
      <DialogContent
        closeLabel={closeLabel}
        className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden p-0 sm:max-w-xl"
      >
        <DialogHeader className="shrink-0 px-6 pb-4 pt-6">
          <DialogTitle className="pr-8 text-xl font-bold tracking-tight">
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 overflow-y-auto px-6 py-1">{children}</div>
        <DialogFooter className="shrink-0 border-t border-border px-6 pb-6 pt-4">
          {footer}
        </DialogFooter>
      </DialogContent>
    );
  }

  return (
    <SheetShell
      side="right"
      title={title}
      description={description}
      closeButton
      closeLabel={closeLabel}
      footer={footer}
      contentClassName="w-full sm:max-w-lg"
    >
      {children}
    </SheetShell>
  );
}
