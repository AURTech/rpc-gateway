"use client";

import { CheckIcon, CopyIcon, Network, TerminalIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { RpcAppDetail } from "@/api/apps/client";
import type {
  RpcGatewayBase,
  RpcGatewayTransport,
} from "@/api/gateways/client";
import type { RpcMethodProtocol } from "@/api/rpc-methods/client";
import { Button } from "@/components/ui/button";
import { ChainIcon } from "@/components/ui/chain-icon";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useGatewaysQuery } from "@/hooks/use-gateways";
import { Link } from "@/i18n/navigation";
import { copyToClipboard } from "@/lib/clipboard";
import { chainLabel, chainProtocol, networkLabel } from "@/lib/rpc-chain";

import { IconButton } from "../../../_components/compact-drawer";
import { AppDetailFrame } from "./app-detail-frame";
import { AppNetworksPanel } from "./app-networks-panel";
import { GatewayApiKeyCopy } from "./gateway-api-key-copy";
import { type AppOverviewTab, useAppOverviewTab } from "./use-app-overview-tab";
import { useGatewayPathKey } from "./use-gateway-path-key";

// The gateway list API caps `size` at 50; an app owns at most one gateway per
// (chain, network) pair (~21 across the registry), so one page covers them all.
const APP_GATEWAYS_SIZE = 50;

/**
 * App "Overview" sub-page - the app home at the bare `/apps/<id>` route, and
 * the app's landing surface: two tabs split it into "Quick Start" (a first-
 * request guide built from the app's endpoint templates) and "Gateway" (the
 * per-network management surface). A fresh app opens on Quick Start; later
 * visits open Gateway. App Usage lives at its own sidebar route.
 */
export function AppOverviewContent({
  appId,
  initialTab,
}: {
  appId: string;
  /** `?tab=` from the route, or undefined when the URL didn't specify one. */
  initialTab?: AppOverviewTab;
}) {
  const pathKeyState = useGatewayPathKey(appId);

  return (
    <AppDetailFrame
      appId={appId}
      headerAction={<GatewayApiKeyCopy pathKeyState={pathKeyState} />}
    >
      {(app) => (
        <AppOverviewBody
          app={app}
          initialTab={initialTab}
          pathKeyState={pathKeyState}
        />
      )}
    </AppDetailFrame>
  );
}

function AppOverviewBody({
  app,
  initialTab,
  pathKeyState,
}: {
  app: RpcAppDetail;
  initialTab?: AppOverviewTab;
  pathKeyState: ReturnType<typeof useGatewayPathKey>;
}) {
  const t = useTranslations("dashboard.apps.detail.overview");
  const { tab, changeTab } = useAppOverviewTab({ appId: app.id, initialTab });

  const tabOptions = useMemo(
    () => [
      { value: "setup" as const, label: t("tabs.setup") },
      { value: "gateways" as const, label: t("tabs.gateways") },
    ],
    [t],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5">
      <Tabs
        mode="tab"
        variant="underline"
        size="lg"
        value={tab}
        onChange={changeTab}
        options={tabOptions}
        ariaLabel={t("tabsAriaLabel")}
        idBase="app-overview-tab"
      />
      {/* Each panel owns its own scroll region, so the tab bar above stays
       * pinned while the content below moves. */}
      <div
        id="app-overview-tab-panel"
        role="tabpanel"
        aria-labelledby={`app-overview-tab-${tab}`}
        className="flex min-h-0 flex-1 flex-col"
      >
        {tab === "setup" ? (
          <AppSetupPanel
            appId={app.id}
            pathKey={pathKeyState.pathKey}
            pathKeyStatus={pathKeyState.status}
          />
        ) : (
          <div className="flex min-h-0 flex-1 flex-col">
            <AppNetworksPanel appId={app.id} pathKeyState={pathKeyState} />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The "Quick Start" tab: the first-request quickstart, or a pointer at the
 * Gateway section while the app has no endpoint to call yet.
 */
function AppSetupPanel({
  appId,
  pathKey,
  pathKeyStatus,
}: {
  appId: string;
  pathKey: string | null;
  pathKeyStatus: ReturnType<typeof useGatewayPathKey>["status"];
}) {
  const gatewaysQuery = useGatewaysQuery({
    app_id: appId,
    enabled: true,
    size: APP_GATEWAYS_SIZE,
  });
  const gateways = useMemo(
    () =>
      gatewaysQuery.data?.items.filter(
        (gateway) => gateway.effective_enabled,
      ) ?? [],
    [gatewaysQuery.data],
  );

  return (
    // Only this region scrolls; the frame's app header and the tab bar stay
    // pinned above.
    <div className="no-scrollbar -mx-2 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-2 pt-1 pb-2">
      {gatewaysQuery.isPending ||
      (gateways.length > 0 && pathKeyStatus === "metadata-loading") ? (
        <QuickstartSkeleton />
      ) : gateways.length === 0 ? (
        <GetStartedCard appId={appId} />
      ) : (
        <QuickstartCard apiKey={pathKey} gateways={gateways} />
      )}
    </div>
  );
}

// Which auth methods a transport can demonstrate. gRPC carries the key as
// call metadata; the HTTP transports take it in the path or a Bearer header.
const TRANSPORT_AUTH_MODES = {
  jsonrpc: ["apiKey", "httpBearer"],
  http_api: ["apiKey", "httpBearer"],
  grpc: ["grpcBearer"],
} as const satisfies Record<RpcGatewayTransport, readonly string[]>;

type AuthMode = (typeof TRANSPORT_AUTH_MODES)[RpcGatewayTransport][number];

// Order the picker by how most users start: JSON-RPC first, gRPC last.
const TRANSPORT_ORDER: readonly RpcGatewayTransport[] = [
  "jsonrpc",
  "http_api",
  "grpc",
];

const SAMPLE_METHOD: Record<RpcMethodProtocol, string> = {
  evm: "eth_blockNumber",
  tron: "eth_blockNumber",
  svm: "getBlockHeight",
  utxo: "getblockcount",
};

/** The transports this gateway actually exposes, in display order. */
function availableTransports(gateway: RpcGatewayBase): RpcGatewayTransport[] {
  return TRANSPORT_ORDER.filter((transport) =>
    gateway.access_points.some((point) => point.transport === transport),
  );
}

function accessUrl(
  gateway: RpcGatewayBase,
  transport: RpcGatewayTransport,
): string | null {
  return (
    gateway.access_points.find((item) => item.transport === transport)?.url ??
    null
  );
}

function sampleBody(method: string): string {
  return JSON.stringify({ jsonrpc: "2.0", id: 1, method, params: [] });
}

function endpointWithApiKey(url: string, apiKey: string | null): string {
  if (!apiKey) return url;
  return url.replace(/\{(?:path|api)_key\}/g, () => apiKey);
}

// Bearer auth calls the gateway root, so drop the trailing key placeholder.
function bearerEndpoint(url: string): string {
  return url.replace(/\/\{(?:path|api)_key\}$/, "");
}

function apiKeyCurl(url: string, method: string): string {
  return [
    "curl --request POST \\",
    `  --url '${url}' \\`,
    "  --header 'Content-Type: application/json' \\",
    `  --data '${sampleBody(method)}'`,
  ].join("\n");
}

function bearerCurl(
  url: string,
  method: string,
  apiKey: string | null,
): string {
  return [
    "curl --request POST \\",
    `  --url '${bearerEndpoint(url)}' \\`,
    `  --header 'Authorization: Bearer ${apiKey ?? "{api_key}"}' \\`,
    "  --header 'Content-Type: application/json' \\",
    `  --data '${sampleBody(method)}'`,
  ].join("\n");
}

function grpcConfig(url: string, apiKey: string | null): string {
  return `endpoint: ${url}
metadata:
  authorization: Bearer ${apiKey ?? "{api_key}"}
method: {service}/{method}`;
}

function networkDisplayName(gateway: RpcGatewayBase): string {
  return `${chainLabel(gateway.chain)} ${networkLabel(gateway.chain, gateway.network)}`;
}

/**
 * First-request quickstart (adapted from the v1 app "Setup" tab): pick a
 * network and a protocol, read that endpoint, and copy a ready-to-run example
 * for the chosen auth method. The App's active API key replaces the endpoint
 * template placeholder when one is available.
 */
function QuickstartCard({
  apiKey,
  gateways,
}: {
  apiKey: string | null;
  gateways: RpcGatewayBase[];
}) {
  const t = useTranslations("dashboard.apps.detail.overview.quickstart");
  const ta = useTranslations("dashboard.apps");

  const [gatewayId, setGatewayId] = useState<string | undefined>(undefined);
  const selected =
    gateways.find((gateway) => gateway.id === gatewayId) ?? gateways[0];

  const transports = availableTransports(selected);
  const [transportChoice, setTransportChoice] = useState<
    RpcGatewayTransport | undefined
  >(undefined);
  // Switching networks can strip the chosen protocol, so fall back rather than
  // hold a transport this gateway doesn't expose.
  const transport =
    transportChoice && transports.includes(transportChoice)
      ? transportChoice
      : transports[0];

  const authModes: readonly AuthMode[] = transport
    ? TRANSPORT_AUTH_MODES[transport]
    : [];
  const [authChoice, setAuthChoice] = useState<AuthMode | undefined>(undefined);
  // Same for auth: gRPC and the HTTP transports share no auth method.
  const authMode =
    authChoice && authModes.includes(authChoice) ? authChoice : authModes[0];

  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    };
  }, []);

  const urlTemplate = transport ? accessUrl(selected, transport) : null;
  const url = urlTemplate
    ? endpointWithApiKey(urlTemplate, apiKey)
    : urlTemplate;
  const method = SAMPLE_METHOD[chainProtocol(selected.chain)];

  const example = !urlTemplate
    ? t("unavailable")
    : authMode === "grpcBearer"
      ? grpcConfig(urlTemplate, apiKey)
      : authMode === "httpBearer"
        ? bearerCurl(urlTemplate, method, apiKey)
        : apiKeyCurl(endpointWithApiKey(urlTemplate, apiKey), method);

  const resetCopied = () => setCopied(false);

  const handleSelectGateway = (value: string) => {
    setGatewayId(value);
    resetCopied();
  };

  const handleSelectTransport = (value: string) => {
    setTransportChoice(value as RpcGatewayTransport);
    resetCopied();
  };

  const handleAuthMode = (value: AuthMode) => {
    setAuthChoice(value);
    resetCopied();
  };

  const handleCopyExample = async () => {
    const ok = await copyToClipboard(example);
    if (ok) toast.success(ta("toast.copyOk"));
    else toast.error(ta("toast.copyError"));
    if (!ok) return;
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), 2000);
  };

  const authOptions = authModes.map((mode) => ({
    value: mode,
    label: t(`auth.${mode}.label`),
  }));

  return (
    <section className="shrink-0 rounded-xl bg-surface p-5 shadow-section">
      <div className="flex max-w-prose flex-col gap-1">
        <h2 className="text-lg font-semibold text-ink-900">{t("title")}</h2>
        <p className="text-md text-ink-500">{t("subtitle")}</p>
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-5 lg:gap-0 lg:divide-x lg:divide-ink-wash">
        <div className="flex flex-col gap-4 lg:col-span-2 lg:pr-6">
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="quickstart-network"
              className="text-sm font-medium text-ink-500"
            >
              {t("network")}
            </label>
            <Select value={selected.id} onValueChange={handleSelectGateway}>
              <SelectTrigger
                id="quickstart-network"
                aria-label={t("selectorLabel")}
                className="h-9 w-full py-0 text-sm"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <ChainIcon
                    chain={selected.chain}
                    network={selected.network}
                    className="size-4"
                  />
                  <SelectValue />
                </span>
              </SelectTrigger>
              <SelectContent className="max-h-72">
                {gateways.map((gateway) => (
                  <SelectItem
                    key={gateway.id}
                    value={gateway.id}
                    icon={
                      <ChainIcon
                        chain={gateway.chain}
                        network={gateway.network}
                        className="size-4"
                      />
                    }
                  >
                    {networkDisplayName(gateway)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="quickstart-protocol"
              className="text-sm font-medium text-ink-500"
            >
              {t("protocol")}
            </label>
            {/* Only the transports this gateway exposes are offered, so the
             * picker can never land on an endpoint that doesn't exist. */}
            <Select
              value={transport ?? ""}
              onValueChange={handleSelectTransport}
              disabled={transports.length === 0}
            >
              <SelectTrigger
                id="quickstart-protocol"
                aria-label={t("protocolLabel")}
                className="h-9 w-full py-0 text-sm"
              >
                <SelectValue placeholder={t("unavailable")} />
              </SelectTrigger>
              <SelectContent>
                {transports.map((item) => (
                  <SelectItem key={item} value={item}>
                    {t(`transport.${item}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-ink-500">
              {t("method")}
            </span>
            <code className="rounded-md bg-ink-wash px-3 py-2 font-mono text-sm text-ink-700">
              {method}
            </code>
          </div>

          <EndpointRow
            label={t("endpointUrl")}
            unavailable={t("unavailable")}
            url={url}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-4 lg:col-span-3 lg:pl-6">
          {authMode ? (
            <>
              <Tabs
                mode="tab"
                value={authMode}
                onChange={handleAuthMode}
                options={authOptions}
                ariaLabel={t("auth.ariaLabel")}
                idBase="quickstart-auth"
              />
              <div
                id="quickstart-auth-panel"
                role="tabpanel"
                aria-labelledby={`quickstart-auth-${authMode}`}
                className="flex flex-col gap-3"
              >
                <p className="text-sm text-ink-500">
                  {t(`auth.${authMode}.description`)}
                </p>
                <CodeBlock
                  code={example}
                  copied={copied}
                  language={authMode === "grpcBearer" ? "CONFIG" : "cURL"}
                  onCopy={handleCopyExample}
                  title={t(`auth.${authMode}.exampleTitle`)}
                />
              </div>
            </>
          ) : (
            <p className="text-sm text-ink-500">{t("unavailable")}</p>
          )}
        </div>
      </div>
    </section>
  );
}

function CodeBlock({
  code,
  copied,
  language,
  onCopy,
  title,
}: {
  code: string;
  copied: boolean;
  language: string;
  onCopy: () => void;
  title: string;
}) {
  const t = useTranslations("dashboard.apps.detail.overview.quickstart");

  return (
    <section
      aria-label={title}
      className="overflow-hidden rounded-lg border border-table-frame bg-white shadow-sm"
    >
      <div className="flex min-h-10 items-center justify-between gap-3 border-table-frame border-b bg-ink-wash px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <TerminalIcon className="size-4 shrink-0 text-ink-400" aria-hidden />
          <span className="truncate font-medium text-sm text-ink-900">
            {title}
          </span>
          <span className="shrink-0 rounded border border-table-frame bg-white px-1.5 py-0.5 font-mono text-2xs text-ink-500">
            {language}
          </span>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          onClick={onCopy}
          aria-label={t("copyExample")}
          className="h-7 text-ink-500 hover:bg-white hover:text-ink-900"
        >
          {copied ? (
            <CheckIcon className="size-3.5" aria-hidden />
          ) : (
            <CopyIcon className="size-3.5" aria-hidden />
          )}
          {copied ? t("copied") : t("copy")}
        </Button>
      </div>
      <pre className="max-h-120 min-h-64 overflow-y-auto bg-white px-4 py-4 font-mono text-sm leading-5 text-ink-800">
        <code className="block whitespace-pre-wrap [overflow-wrap:anywhere]">
          {code}
        </code>
      </pre>
    </section>
  );
}

function EndpointRow({
  label,
  unavailable,
  url,
}: {
  label: string;
  unavailable: string;
  url: string | null | undefined;
}) {
  const t = useTranslations("dashboard.apps.detail.overview.quickstart");
  const ta = useTranslations("dashboard.apps");

  const handleCopy = async () => {
    if (!url) return;
    const ok = await copyToClipboard(url);
    if (ok) toast.success(ta("toast.copyOk"));
    else toast.error(ta("toast.copyError"));
  };

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-ink-500">{label}</span>
      <div className="flex min-w-0 items-center gap-1 rounded-md bg-ink-wash px-3 py-2">
        <code className="min-w-0 flex-1 truncate font-mono text-sm text-ink-700">
          {url ?? unavailable}
        </code>
        {url ? (
          <IconButton
            ariaLabel={t("copyEndpoint", { name: label })}
            onClick={handleCopy}
            className="shrink-0"
          >
            <CopyIcon className="size-3.5" aria-hidden />
          </IconButton>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Shown instead of the quickstart while the app has no gateway at all - there's
 * no endpoint to call yet, so point at the Gateway section to add one.
 */
function GetStartedCard({ appId }: { appId: string }) {
  const t = useTranslations("dashboard.apps.detail.overview.empty");

  return (
    <section className="flex shrink-0 flex-col items-center gap-2 rounded-xl bg-surface px-6 py-12 text-center shadow-section">
      <Network className="size-8 text-ink-400" aria-hidden />
      <p className="text-lg font-semibold text-ink-900">{t("title")}</p>
      <p className="max-w-prose-narrow text-md text-ink-500">{t("body")}</p>
      <Link
        href={`/dashboard/apps/${appId}?tab=gateways`}
        className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
      >
        {t("cta")}
      </Link>
    </section>
  );
}

function QuickstartSkeleton() {
  return (
    <div className="flex flex-col gap-4 rounded-xl bg-surface p-5 shadow-section">
      <Skeleton className="h-6 w-40" />
      <Skeleton className="h-9 w-full max-w-xs" />
      <Skeleton className="h-64 w-full rounded-lg" />
    </div>
  );
}
