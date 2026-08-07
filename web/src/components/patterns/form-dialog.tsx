"use client";

import type { FormEvent, ReactNode } from "react";

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

type FormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  /** Form fields. Rendered inside the `<form>` between header and footer. */
  children: ReactNode;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  submitLabel: ReactNode;
  cancelLabel: ReactNode;
  /** Submission in flight: disables actions, blocks close, shows pending label. */
  submitting?: boolean;
  /** Gate the submit button (validity). Defaults to enabled. */
  canSubmit?: boolean;
  submittingLabel?: ReactNode;
  submitVariant?: React.ComponentProps<typeof Button>["variant"];
  contentClassName?: string;
  noValidate?: boolean;
  /** Accessible label for the icon-only close action. */
  closeLabel?: string;
};

/**
 * Standard create/edit dialog: titled form with cancel + submit footer, the
 * built-in dialog close button, and close blocked while submitting. Replaces
 * the per-dialog hand-rolled close button and footer chrome.
 */
export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  onSubmit,
  submitLabel,
  cancelLabel,
  submitting = false,
  canSubmit = true,
  submittingLabel,
  submitVariant = "default",
  contentClassName,
  noValidate = false,
  closeLabel,
}: FormDialogProps) {
  // Block close (overlay click / Esc / X) mid-submit.
  const handleOpenChange = (next: boolean) => {
    if (submitting) return;
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        closeLabel={closeLabel}
        className={cn(
          "max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0",
          contentClassName,
        )}
      >
        <DialogHeader className="shrink-0 px-6 pb-4 pt-6">
          <DialogTitle className="pr-8 text-xl font-bold tracking-tight">
            {title}
          </DialogTitle>
          {description ? (
            <DialogDescription>{description}</DialogDescription>
          ) : null}
        </DialogHeader>
        <form
          className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto]"
          noValidate={noValidate}
          onSubmit={onSubmit}
        >
          <div className="flex min-h-0 flex-col gap-4 overflow-y-auto px-6 py-1">
            {children}
          </div>
          <DialogFooter className="shrink-0 border-t border-border px-6 pb-6 pt-4">
            <Button
              type="button"
              variant="ghost"
              onClick={() => handleOpenChange(false)}
              disabled={submitting}
            >
              {cancelLabel}
            </Button>
            <Button
              type="submit"
              variant={submitVariant}
              disabled={!canSubmit || submitting}
            >
              {submitting ? (submittingLabel ?? submitLabel) : submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
