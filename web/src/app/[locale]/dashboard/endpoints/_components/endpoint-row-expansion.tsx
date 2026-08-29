"use client";

import { Check, Copy, ExternalLink, Link2Off } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { Endpoint, EndpointRouteBinding } from "@/api/endpoints/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import {
  useDeleteEndpointRouteBindingMutation,
  useEndpointQuery,
  useEndpointRouteBindingsQuery,
} from "@/hooks/use-endpoints";
import { Link } from "@/i18n/navigation";
import { copyToClipboard } from "@/lib/clipboard";
import { cn } from "@/lib/utils";
import { EndpointInlineEditor } from "./endpoint-inline-editor";

type ExpansionTab = "endpoint" | "bindings";

// Inactive panels stay mounted and keep their grid cell so the row height does
// not jump between tabs. `transition-none` on the subtree is what stops the
// shared Button's `transition-all` from animating the inherited `visibility`
// flip, which left its copy button painted over the other tab for ~150ms.
const HIDDEN_PANEL = "invisible pointer-events-none [&_*]:transition-none";

interface EndpointRowExpansionProps {
  endpoint: Endpoint;
  editing: boolean;
  onFinishEditing: () => void;
}

function EndpointRowExpansion({
  endpoint,
  editing,
  onFinishEditing,
}: EndpointRowExpansionProps) {
  const t = useTranslations("dashboard.endpoints");
  const [tab, setTab] = useState<ExpansionTab>("endpoint");
  const [bindingsVisited, setBindingsVisited] = useState(false);
  const [bindingsTotal, setBindingsTotal] = useState<number | null>(null);

  function changeTab(next: ExpansionTab) {
    if (next === "bindings") setBindingsVisited(true);
    setTab(next);
  }

  if (editing) {
    return (
      <EndpointPanel
        endpoint={endpoint}
        editing
        onFinishEditing={onFinishEditing}
      />
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <Tabs
        mode="tab"
        value={tab}
        onChange={changeTab}
        options={[
          { value: "endpoint", label: t("rowExpansion.tabs.endpoint") },
          {
            value: "bindings",
            label:
              bindingsTotal === null
                ? t("rowExpansion.tabs.bindings")
                : t("rowExpansion.tabs.bindingsCount", {
                    count: bindingsTotal,
                  }),
          },
        ]}
        ariaLabel={t("rowExpansion.tabs.label")}
        idBase={`endpoint-${endpoint.id}-expansion-tab`}
        variant="underline"
      />

      <div
        id={`endpoint-${endpoint.id}-expansion-tab-panel`}
        role="tabpanel"
        aria-labelledby={`endpoint-${endpoint.id}-expansion-tab-${tab}`}
        className="grid min-w-0"
      >
        <div
          className={cn(
            "col-start-1 row-start-1 min-w-0",
            tab !== "endpoint" && HIDDEN_PANEL,
          )}
          aria-hidden={tab !== "endpoint"}
          inert={tab !== "endpoint" ? true : undefined}
        >
          <EndpointPanel
            endpoint={endpoint}
            editing={false}
            onFinishEditing={onFinishEditing}
          />
        </div>

        {bindingsVisited ? (
          <div
            className={cn(
              "col-start-1 row-start-1 min-w-0",
              tab !== "bindings" && HIDDEN_PANEL,
            )}
            aria-hidden={tab !== "bindings"}
            inert={tab !== "bindings" ? true : undefined}
          >
            <BindingsPanel
              endpoint={endpoint}
              onTotalChange={setBindingsTotal}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function EndpointPanel({
  endpoint,
  editing,
  onFinishEditing,
}: {
  endpoint: Endpoint;
  editing: boolean;
  onFinishEditing: () => void;
}) {
  const t = useTranslations("dashboard.endpoints");
  const endpointQuery = useEndpointQuery(
    endpoint.id,
    editing ? undefined : endpoint,
  );

  if (endpointQuery.isLoading) return <EndpointFactsSkeleton />;
  if (endpointQuery.isError || !endpointQuery.data) {
    return (
      <InlineError
        title={t("rowExpansion.details.errorTitle")}
        body={t("rowExpansion.details.errorBody")}
        retryLabel={t("rowExpansion.retry")}
        onRetry={() => endpointQuery.refetch()}
      />
    );
  }

  return (
    <EndpointInlineEditor
      key={`${endpointQuery.data.id}:${endpointQuery.data.version}`}
      endpoint={endpointQuery.data}
      editing={editing}
      onFinishEditing={onFinishEditing}
      onReload={async () => {
        const result = await endpointQuery.refetch();
        return result.data ?? null;
      }}
    />
  );
}

function BindingsPanel({
  endpoint,
  onTotalChange,
}: {
  endpoint: Endpoint;
  onTotalChange: (total: number) => void;
}) {
  const t = useTranslations("dashboard.endpoints");
  const bindingsQuery = useEndpointRouteBindingsQuery(endpoint.id);
  const unbind = useDeleteEndpointRouteBindingMutation();
  const [unbindTarget, setUnbindTarget] = useState<EndpointRouteBinding | null>(
    null,
  );

  useEffect(() => {
    if (bindingsQuery.data) onTotalChange(bindingsQuery.data.total);
  }, [bindingsQuery.data, onTotalChange]);

  async function removeBinding(binding: EndpointRouteBinding) {
    try {
      await unbind.mutateAsync({ endpointId: endpoint.id, binding });
      setUnbindTarget(null);
      toast.success(t("rowExpansion.bindings.unbound"));
    } catch {
      toast.error(t("rowExpansion.bindings.unbindError"));
    }
  }

  function getUnbindDescription(binding: EndpointRouteBinding) {
    if (binding.target_count > 1) {
      return t("rowExpansion.dialog.descriptionRemaining", {
        gateway: binding.gateway.name,
        count: binding.target_count - 1,
      });
    }
    if (binding.route_type === "jsonrpc_method") {
      return t("rowExpansion.dialog.descriptionDeleteMethod", {
        gateway: binding.gateway.name,
      });
    }
    return t("rowExpansion.dialog.descriptionEmptyRoute", {
      gateway: binding.gateway.name,
      route: t(
        binding.route_type === "http_api"
          ? "rowExpansion.bindings.httpApiRoute"
          : "rowExpansion.bindings.defaultRoute",
      ),
    });
  }

  return (
    <div className="min-w-0">
      <section aria-labelledby={`endpoint-${endpoint.id}-bindings-title`}>
        <h3 id={`endpoint-${endpoint.id}-bindings-title`} className="sr-only">
          {t("rowExpansion.bindings.title")}
        </h3>

        {bindingsQuery.isLoading ? (
          <BindingsSkeleton />
        ) : bindingsQuery.isError ? (
          <InlineError
            title={t("rowExpansion.bindings.errorTitle")}
            body={t("rowExpansion.bindings.errorBody")}
            retryLabel={t("rowExpansion.retry")}
            onRetry={() => bindingsQuery.refetch()}
          />
        ) : bindingsQuery.data?.items.length ? (
          <div>
            <div
              className="grid grid-cols-12 gap-x-8 border-b border-table-frame pb-2 text-xs font-medium text-ink-500"
              aria-hidden
            >
              <span className="col-span-3">
                {t("rowExpansion.bindings.columns.gateway")}
              </span>
              <span className="col-span-5">
                {t("rowExpansion.bindings.columns.route")}
              </span>
              <span className="col-span-2">
                {t("rowExpansion.bindings.columns.routing")}
              </span>
              <span className="col-span-2 text-right">
                {t("rowExpansion.bindings.columns.action")}
              </span>
            </div>
            <ul className="divide-y divide-table-frame">
              {bindingsQuery.data.items.map((binding) => (
                <BindingItem
                  key={`${binding.route_type}:${binding.route_id}`}
                  binding={binding}
                  busy={unbind.isPending}
                  onUnbind={() => setUnbindTarget(binding)}
                />
              ))}
            </ul>
          </div>
        ) : (
          <div className="rounded-lg bg-ink-wash px-5 py-4">
            <p className="text-sm font-medium text-ink-900">
              {t("rowExpansion.bindings.emptyTitle")}
            </p>
            <p className="mt-1 text-sm text-ink-500">
              {t("rowExpansion.bindings.emptyBody")}
            </p>
          </div>
        )}
      </section>

      <Dialog
        open={unbindTarget !== null}
        onOpenChange={(open) => {
          if (!open && !unbind.isPending) setUnbindTarget(null);
        }}
      >
        <DialogContent closeLabel={t("rowExpansion.dialog.close")}>
          <DialogHeader>
            <DialogTitle>{t("rowExpansion.dialog.title")}</DialogTitle>
            <DialogDescription>
              {unbindTarget ? getUnbindDescription(unbindTarget) : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              disabled={unbind.isPending}
              onClick={() => setUnbindTarget(null)}
            >
              {t("rowExpansion.dialog.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={!unbindTarget || unbind.isPending}
              onClick={() => unbindTarget && removeBinding(unbindTarget)}
            >
              {unbind.isPending
                ? t("rowExpansion.dialog.unbinding")
                : t("rowExpansion.dialog.unbind")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function BindingItem({
  binding,
  busy,
  onUnbind,
}: {
  binding: EndpointRouteBinding;
  busy: boolean;
  onUnbind: () => void;
}) {
  const t = useTranslations("dashboard.endpoints");
  const transport = binding.route_type === "http_api" ? "http_api" : "jsonrpc";
  const gatewayHref = `/dashboard/apps/${binding.gateway.app_id}/gateways/${binding.gateway.id}?transport=${transport}`;
  const routeLabel = t(
    binding.route_type === "jsonrpc_method"
      ? "rowExpansion.bindings.methodRoute"
      : binding.route_type === "http_api"
        ? "rowExpansion.bindings.httpApiRoute"
        : "rowExpansion.bindings.defaultRoute",
  );

  return (
    <li className="grid grid-cols-12 items-center gap-x-8 py-3.5">
      <div className="col-span-3 min-w-0">
        <Link
          href={gatewayHref}
          className="inline-flex max-w-full items-center gap-1.5 rounded-sm font-medium text-ink-900 hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
        >
          <span className="truncate">{binding.gateway.name}</span>
          <ExternalLink className="size-3 shrink-0 text-ink-400" aria-hidden />
        </Link>
      </div>
      <div className="col-span-5 min-w-0">
        <div className="flex min-w-0 items-baseline gap-2 text-sm text-ink-700">
          <span className="shrink-0 font-medium text-ink-900">
            {routeLabel}
          </span>
          {binding.route_type === "jsonrpc_method" ? (
            <MethodSummary methods={binding.methods} />
          ) : null}
        </div>
        <RouteId routeId={binding.route_id} />
      </div>
      <div className="col-span-2 min-w-0">
        <p className="truncate text-sm text-ink-700">
          {t(`rowExpansion.bindings.strategy.${binding.strategy_type}`)}
        </p>
        <p
          className={cn(
            "mt-0.5 text-xs tabular-nums",
            binding.target_count === 1 ? "text-warning" : "text-ink-500",
          )}
        >
          {binding.target_count === 1
            ? t("rowExpansion.bindings.lastTarget")
            : t("rowExpansion.bindings.targetCount", {
                count: binding.target_count,
              })}
        </p>
      </div>
      <div className="col-span-2 flex justify-end">
        <Button size="sm" variant="ghost" disabled={busy} onClick={onUnbind}>
          <Link2Off aria-hidden />
          {t("rowExpansion.bindings.unbind")}
        </Button>
      </div>
    </li>
  );
}

function MethodSummary({ methods }: { methods: string[] }) {
  const t = useTranslations("dashboard.endpoints");
  const visibleMethods = methods.slice(0, 2);
  const hiddenCount = methods.length - visibleMethods.length;
  const fullSummary = methods.join(", ");

  if (!methods.length) {
    return (
      <span className="truncate text-ink-500">
        {t("rowExpansion.bindings.noMethods")}
      </span>
    );
  }

  return (
    <span className="flex min-w-0 items-baseline gap-1.5">
      <span
        className="truncate font-mono text-xs text-ink-500"
        title={fullSummary}
      >
        {visibleMethods.join(", ")}
      </span>
      {hiddenCount > 0 ? (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="shrink-0 rounded-sm text-xs font-medium text-brand outline-none hover:underline focus-visible:ring-2 focus-visible:ring-brand/30"
              aria-label={t("rowExpansion.bindings.showAllMethods", {
                count: methods.length,
              })}
            >
              {t("rowExpansion.bindings.moreMethods", { count: hiddenCount })}
            </button>
          </PopoverTrigger>
          <PopoverContent
            className="max-h-64 w-72 overflow-y-auto p-2"
            align="start"
          >
            <p className="px-2 py-1 text-xs font-medium text-ink-500">
              {t("rowExpansion.bindings.methods")}
            </p>
            <ul className="py-1">
              {methods.map((method) => (
                <li
                  key={method}
                  className="rounded-md px-2 py-1.5 font-mono text-xs text-ink-700"
                >
                  {method}
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      ) : null}
    </span>
  );
}

function RouteId({ routeId }: { routeId: string }) {
  const t = useTranslations("dashboard.endpoints");
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  async function copyRouteId() {
    if (!(await copyToClipboard(routeId))) {
      toast.error(t("rowExpansion.bindings.copyError"));
      return;
    }
    toast.success(t("rowExpansion.bindings.routeIdCopied"));
    setCopied(true);
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setCopied(false), 1800);
  }

  return (
    <span className="group/route-id mt-0.5 flex min-w-0 items-center gap-1">
      <span className="truncate font-mono text-xs text-ink-500" title={routeId}>
        {routeId}
      </span>
      <Button
        type="button"
        size="icon-xs"
        variant="ghost"
        className="opacity-0 transition-opacity group-hover/route-id:opacity-100 group-focus-within/route-id:opacity-100 focus-visible:opacity-100"
        onClick={() => void copyRouteId()}
        aria-label={t("rowExpansion.bindings.copyRouteId")}
        title={t("rowExpansion.bindings.copyRouteId")}
      >
        {copied ? (
          <Check className="text-positive" aria-hidden />
        ) : (
          <Copy aria-hidden />
        )}
      </Button>
    </span>
  );
}

function InlineError({
  title,
  body,
  retryLabel,
  onRetry,
}: {
  title: string;
  body: string;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <div className="mt-3 flex items-center justify-between gap-6 rounded-lg bg-danger-soft px-5 py-4">
      <div>
        <p className="text-sm font-semibold text-danger">{title}</p>
        <p className="mt-1 text-sm text-danger/80">{body}</p>
      </div>
      <Button className="shrink-0" size="sm" variant="ghost" onClick={onRetry}>
        {retryLabel}
      </Button>
    </div>
  );
}

function EndpointFactsSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-8">
        <div className="grid min-w-0 flex-1 grid-cols-12 gap-x-8">
          <div className="col-span-7 space-y-2">
            <Skeleton className="h-3 w-12" />
            <Skeleton className="h-5 w-48" />
          </div>
          <div className="col-span-5 space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-5 w-24" />
          </div>
        </div>
        <Skeleton className="h-8 w-16" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-5 w-3/4" />
      </div>
      <div className="grid grid-cols-12 gap-x-8">
        {[
          { id: "provider", className: "col-span-4" },
          { id: "external-id", className: "col-span-3" },
          { id: "sync-status", className: "col-span-2" },
          { id: "last-seen", className: "col-span-3" },
        ].map(({ id, className }) => (
          <div key={id} className={`${className} space-y-2`}>
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
      <div className="flex gap-6 border-t border-table-frame pt-4">
        <Skeleton className="h-3 w-48" />
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-3 w-20" />
      </div>
    </div>
  );
}

function BindingsSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-12 w-full" />
    </div>
  );
}

export { EndpointRowExpansion };
