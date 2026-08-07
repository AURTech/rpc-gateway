"use client";

import { useTranslations } from "next-intl";

import { Input } from "@/components/ui/input";
import { isValidWeight, WEIGHT_MAX } from "@/lib/endpoint-weights";
import { cn } from "@/lib/utils";

/**
 * Compact integer weight input for load balancing. Users edit the raw target
 * weight (1–1000); the read-only share preview normalizes weights into a
 * percentage. The value maps directly to the API `weight` field.
 */
export function WeightRatioInput({
  value,
  onChange,
  disabled,
  ariaLabel,
}: {
  value: number | undefined;
  onChange: (next: number) => void;
  disabled?: boolean;
  ariaLabel: string;
}) {
  const invalid = !isValidWeight(value);
  return (
    <Input
      type="text"
      inputMode="numeric"
      aria-label={ariaLabel}
      aria-invalid={invalid || undefined}
      disabled={disabled}
      value={value && value > 0 ? String(value) : ""}
      onChange={(e) => {
        const digits = e.target.value.replace(/\D/g, "").slice(0, 4);
        const next = digits === "" ? 0 : Math.min(WEIGHT_MAX, Number(digits));
        onChange(next);
      }}
      className={cn(
        "h-9 w-16 shrink-0 px-2 py-2 text-right text-sm tabular-nums",
        invalid && "ring-2 ring-danger-soft",
      )}
    />
  );
}

/**
 * Read-only normalized share preview for a weighted endpoint.
 */
export function WeightShare({ percent }: { percent: number | undefined }) {
  const t = useTranslations("dashboard.gateways");
  return (
    <p
      className={cn(
        "w-16 shrink-0 text-right text-2xs font-medium tabular-nums",
        percent === undefined ? "text-ink-400" : "text-ink-500",
      )}
    >
      {percent === undefined
        ? t("weights.shareUnavailable")
        : t("weights.share", { percent })}
    </p>
  );
}
