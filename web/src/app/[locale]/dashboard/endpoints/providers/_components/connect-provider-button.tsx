"use client";

import { PlugZap } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ComponentProps } from "react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useRouter } from "@/i18n/navigation";

import { ConnectProviderFlow } from "./connect-provider-flow";

function providerWorkspaceUrl(id: string, settings = false): string {
  const encodedId = encodeURIComponent(id);
  return `/dashboard/endpoints?workspace=providers&expandedProvider=${encodedId}${settings ? `&providerSettings=${encodedId}` : ""}`;
}

function ConnectProviderButton({
  label,
  size = "default",
  showIcon = true,
  variant = "default",
}: {
  label: string;
  size?: ComponentProps<typeof Button>["size"];
  showIcon?: boolean;
  variant?: ComponentProps<typeof Button>["variant"];
}) {
  const t = useTranslations("dashboard.endpointProviders.onboarding");
  const router = useRouter();
  const [open, setOpen] = useState(false);

  function finish(id: string, settings = false) {
    setOpen(false);
    router.push(providerWorkspaceUrl(id, settings));
  }

  return (
    <>
      <Button
        type="button"
        size={size}
        variant={variant}
        onClick={() => setOpen(true)}
      >
        {showIcon ? <PlugZap aria-hidden /> : null}
        {label}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl"
          closeLabel={t("close")}
        >
          <ConnectProviderFlow
            onComplete={(id) => finish(id)}
            onFixApiKey={(id) => finish(id, true)}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

export { ConnectProviderButton };
