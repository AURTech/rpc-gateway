"use client";

import { Plus } from "lucide-react";
import type { ComponentProps } from "react";
import { useState } from "react";

import type { EndpointProtocol } from "@/api/endpoints/client";
import { Button } from "@/components/ui/button";
import { useIsAdmin } from "@/hooks/use-is-admin";
import type { Chain, Network } from "@/lib/blockchain";

import { EditEndpointSheet } from "./edit-endpoint-sheet";

/**
 * Shared "New endpoint" CTA. Opens the endpoint form in create mode using the
 * requested presentation; the create mutation invalidates endpoint lists on
 * success. Endpoints are account-owned for users and admins alike, so the CTA
 * shows for either identity once it resolves.
 */
export function NewEndpointButton({
  className,
  disabled,
  initialChain,
  initialNetwork,
  initialProtocol,
  label,
  presentation = "sheet",
  size = "xl",
  showIcon = true,
  variant,
}: {
  className?: ComponentProps<typeof Button>["className"];
  disabled?: boolean;
  initialChain?: Chain;
  initialNetwork?: Network;
  initialProtocol?: EndpointProtocol;
  label: string;
  presentation?: "dialog" | "sheet";
  size?: ComponentProps<typeof Button>["size"];
  showIcon?: boolean;
  variant?: ComponentProps<typeof Button>["variant"];
}) {
  const [open, setOpen] = useState(false);
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
        data-action="new-endpoint"
      >
        {showIcon ? <Plus className="size-4" aria-hidden /> : null}
        {label}
      </Button>
      <EditEndpointSheet
        open={open}
        onOpenChange={setOpen}
        initialChain={initialChain}
        initialNetwork={initialNetwork}
        initialProtocol={initialProtocol}
        presentation={presentation}
      />
    </>
  );
}
