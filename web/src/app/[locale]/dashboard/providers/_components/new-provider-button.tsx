"use client";

import { Plus } from "lucide-react";
import type { ComponentProps } from "react";
import { useState } from "react";

import type { RpcProvider } from "@/api/providers/client";
import { Button } from "@/components/ui/button";
import { useIsAdmin } from "@/hooks/use-is-admin";

import { CreateProviderDialog } from "./create-provider-dialog";

/**
 * Shared "New provider" CTA. Opens the create dialog in the caller's styling;
 * the create mutation invalidates provider lists on success and hands the fresh
 * provider to `onCreated`, so callers embedding this next to a picker can
 * select it right away.
 */
export function NewProviderButton({
  className,
  disabled,
  label,
  onCreated,
  showIcon = true,
  size = "xl",
  variant,
}: {
  className?: ComponentProps<typeof Button>["className"];
  disabled?: boolean;
  label: string;
  onCreated?: (provider: RpcProvider) => void;
  showIcon?: boolean;
  size?: ComponentProps<typeof Button>["size"];
  variant?: ComponentProps<typeof Button>["variant"];
}) {
  const [open, setOpen] = useState(false);
  // Providers are account-owned for both users and admins, so the CTA shows for
  // either identity — we just wait until identity resolves to avoid a flash.
  const { isResolved } = useIsAdmin();

  if (!isResolved) return null;

  return (
    <>
      <Button
        type="button"
        size={size}
        variant={variant}
        className={className}
        disabled={disabled}
        onClick={() => setOpen(true)}
        data-action="new-provider"
      >
        {showIcon ? <Plus className="size-4" aria-hidden /> : null}
        {label}
      </Button>
      <CreateProviderDialog
        open={open}
        onOpenChange={setOpen}
        onCreated={onCreated}
      />
    </>
  );
}
