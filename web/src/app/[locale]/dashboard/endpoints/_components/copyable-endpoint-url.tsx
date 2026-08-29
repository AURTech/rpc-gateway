"use client";

import { Check, Copy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { copyToClipboard } from "@/lib/clipboard";
import { cn } from "@/lib/utils";

interface CopyableEndpointUrlProps {
  url: string;
  className?: string;
}

interface EndpointUrlCopyButtonProps {
  url: string;
  className?: string;
}

export function EndpointUrlCopyButton({
  url,
  className,
}: EndpointUrlCopyButtonProps) {
  const t = useTranslations("dashboard.endpoints.fields");
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  async function copyUrl() {
    const ok = await copyToClipboard(url);
    if (!ok) {
      toast.error(t("copyError"));
      return;
    }
    toast.success(t("endpointCopied"));
    setCopied(true);
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setCopied(false), 1800);
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      disabled={!url}
      onClick={() => void copyUrl()}
      aria-label={t("copyEndpoint")}
      title={t("copyEndpoint")}
      className={cn("shrink-0", className)}
    >
      {copied ? (
        <Check className="text-positive" aria-hidden />
      ) : (
        <Copy aria-hidden />
      )}
    </Button>
  );
}

export function CopyableEndpointUrl({
  url,
  className,
}: CopyableEndpointUrlProps) {
  return (
    <span
      className={cn(
        "group/url flex min-w-0 max-w-full items-center gap-1",
        className,
      )}
    >
      <span
        className="min-w-0 truncate whitespace-nowrap font-mono text-xs leading-5 text-ink-500"
        title={url}
      >
        {url}
      </span>
      <EndpointUrlCopyButton
        url={url}
        className="opacity-0 transition-opacity group-hover/url:opacity-100 group-focus-within/url:opacity-100 focus-visible:opacity-100"
      />
    </span>
  );
}
