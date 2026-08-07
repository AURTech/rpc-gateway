"use client";

import { CheckIcon, CopyIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { copyToClipboard } from "@/lib/clipboard";
import { cn } from "@/lib/utils";

import type { useGatewayPathKey } from "./use-gateway-path-key";

type GatewayPathKeyState = ReturnType<typeof useGatewayPathKey>;

/** Displays and copies the complete App API key. */
export function GatewayApiKeyCopy({
  pathKeyState,
}: {
  pathKeyState: GatewayPathKeyState;
}) {
  const t = useTranslations("dashboard.apps");
  const pathKeyT = useTranslations("dashboard.apps.detail.networks.pathKey");
  const { pathKey, refetchKeys, status } = pathKeyState;
  const pending = status === "metadata-loading";
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  const handleCopy = async () => {
    if (status === "metadata-error") {
      toast.error(pathKeyT("metadataError"));
      await refetchKeys();
      return;
    }
    if (status === "missing") {
      toast.error(pathKeyT("missing"));
      return;
    }

    if (!pathKey) return;

    const copied = await copyToClipboard(pathKey);
    if (!copied) {
      toast.error(t("toast.copyError"));
      return;
    }

    setCopied(true);
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setCopied(false), 2500);
  };

  const value =
    status === "metadata-loading"
      ? pathKeyT("loading")
      : status === "metadata-error"
        ? pathKeyT("metadataError")
        : status === "missing"
          ? pathKeyT("missing")
          : pathKey;

  return (
    <div
      className="grid w-full min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-stretch rounded-lg bg-ink-wash sm:w-80"
      data-state={status}
    >
      <span className="flex items-center rounded-s-lg px-2.5 text-xs font-semibold whitespace-nowrap text-ink-500">
        {pathKeyT("label")}
      </span>
      <code
        className={cn(
          "min-w-0 self-center truncate px-2.5 font-mono text-xs leading-4 text-ink-700",
          status !== "available" && "font-sans text-xs text-ink-500",
        )}
        title={status === "available" ? (pathKey ?? undefined) : undefined}
      >
        {value}
      </code>
      <button
        type="button"
        onClick={() => void handleCopy()}
        disabled={pending}
        aria-label={copied ? pathKeyT("copied") : t("actions.copyPathKey")}
        title={copied ? pathKeyT("copied") : t("actions.copyPathKey")}
        className="flex size-9 shrink-0 items-center justify-center rounded-e-lg text-ink-500 transition-colors hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-inset active:bg-brand/15 disabled:cursor-not-allowed disabled:text-ink-400 disabled:opacity-60"
      >
        {copied ? (
          <CheckIcon className="size-4 text-positive" aria-hidden />
        ) : (
          <CopyIcon className="size-4" aria-hidden />
        )}
      </button>
      <span className="sr-only" aria-live="polite">
        {copied ? pathKeyT("copied") : ""}
      </span>
    </div>
  );
}
