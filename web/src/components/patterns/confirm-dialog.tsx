"use client";

import type { ReactNode } from "react";

import { SwapLabel } from "@/components/patterns/swap-label";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type ConfirmDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  /** Optional icon shown above the title, tinted by the destructive flag. */
  icon?: ReactNode;
  /** Optional extra content between description and footer. */
  children?: ReactNode;
  onConfirm: () => void;
  confirmLabel: ReactNode;
  cancelLabel: ReactNode;
  /** Confirmation in flight: disables actions, blocks close. */
  confirming?: boolean;
  confirmingLabel?: ReactNode;
  /** Style the confirm action as destructive (delete/revoke). Defaults true. */
  destructive?: boolean;
  contentClassName?: string;
};

/**
 * Confirmation dialog for destructive or irreversible actions (delete, revoke).
 * Shares the dialog chrome with {@link FormDialog} but commits via a button
 * click rather than a form submit.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  icon,
  children,
  onConfirm,
  confirmLabel,
  cancelLabel,
  confirming = false,
  confirmingLabel,
  destructive = true,
  contentClassName,
}: ConfirmDialogProps) {
  const handleOpenChange = (next: boolean) => {
    if (confirming) return;
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className={cn("gap-5", contentClassName)}>
        {icon ? (
          <div
            aria-hidden
            data-slot="confirm-dialog-icon"
            className={cn(
              "inline-flex size-10 items-center justify-center rounded-xl [&_svg:not([class*='size-'])]:size-5",
              destructive
                ? "bg-danger-soft text-danger"
                : "bg-brand-soft text-brand",
            )}
          >
            {icon}
          </div>
        ) : null}
        <DialogHeader>
          <DialogTitle className="pr-8 text-xl font-bold tracking-tight">
            {title}
          </DialogTitle>
          {description ? (
            <DialogDescription>{description}</DialogDescription>
          ) : null}
        </DialogHeader>
        {children}
        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => handleOpenChange(false)}
            disabled={confirming}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            onClick={onConfirm}
            disabled={confirming}
          >
            <SwapLabel swapKey={confirming ? "confirming" : "idle"}>
              {confirming ? (confirmingLabel ?? confirmLabel) : confirmLabel}
            </SwapLabel>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
