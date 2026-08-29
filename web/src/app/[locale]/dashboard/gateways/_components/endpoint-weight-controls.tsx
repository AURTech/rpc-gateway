"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import {
  clampWeight,
  isValidWeight,
  WEIGHT_MAX,
  WEIGHT_MIN,
} from "@/lib/endpoint-weights";
import { cn } from "@/lib/utils";

/**
 * Compact integer weight input for load balancing. Users edit the raw target
 * weight (1–1000); the read-only share preview normalizes weights into an
 * expected percentage. The value maps directly to the API `weight` field.
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
  const [draft, setDraft] = useState(() => displayWeight(value));
  const [editing, setEditing] = useState(false);
  const initialValue = useRef<number | undefined>(value);
  const skipBlurCommit = useRef(false);
  const numericDraft = draft === "" ? undefined : Number(draft);
  const invalid = !isValidWeight(numericDraft);

  useEffect(() => {
    if (!editing) setDraft(displayWeight(value));
  }, [editing, value]);

  const updateDraft = (nextDraft: string) => {
    setDraft(nextDraft);
    onChange(nextDraft === "" ? 0 : Number(nextDraft));
  };

  const commit = () => {
    const candidate =
      draft === "" ? initialValue.current : Number.parseInt(draft, 10);
    const next = clampWeight(candidate);
    setDraft(String(next));
    onChange(next);
    setEditing(false);
  };

  const restore = () => {
    const next = isValidWeight(initialValue.current)
      ? (initialValue.current as number)
      : clampWeight(value);
    skipBlurCommit.current = true;
    setDraft(String(next));
    onChange(next);
    setEditing(false);
  };

  return (
    <div className="relative w-14 shrink-0">
      <Input
        type="text"
        inputMode="numeric"
        autoComplete="off"
        spellCheck={false}
        mono
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        disabled={disabled}
        value={draft}
        onFocus={(event) => {
          initialValue.current = value;
          setEditing(true);
          event.currentTarget.select();
        }}
        onClick={(event) => event.currentTarget.select()}
        onChange={(event) => {
          const digits = event.target.value.replace(/\D/g, "").slice(0, 4);
          updateDraft(digits);
        }}
        onBlur={() => {
          if (skipBlurCommit.current) {
            skipBlurCommit.current = false;
            return;
          }
          commit();
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            event.currentTarget.blur();
            return;
          }
          if (event.key === "Escape") {
            event.preventDefault();
            restore();
            event.currentTarget.blur();
            return;
          }
          if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;

          event.preventDefault();
          const step = event.shiftKey ? 10 : 1;
          const direction = event.key === "ArrowUp" ? 1 : -1;
          const base = isValidWeight(numericDraft)
            ? (numericDraft as number)
            : isValidWeight(value)
              ? (value as number)
              : WEIGHT_MIN;
          const next = Math.min(
            WEIGHT_MAX,
            Math.max(WEIGHT_MIN, base + direction * step),
          );
          updateDraft(String(next));
        }}
        className="h-8 w-14 py-0 pr-5 pl-2 text-right text-sm font-medium tabular-nums"
      />
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-y-0 right-2 flex items-center font-mono text-xs text-ink-400",
          disabled && "opacity-60",
        )}
      >
        ×
      </span>
    </div>
  );
}

/**
 * Read-only normalized expected-share preview for a weighted endpoint.
 */
export function WeightShare({ percent }: { percent: number | undefined }) {
  const t = useTranslations("dashboard.gateways");
  return (
    <p
      className={cn(
        "w-14 shrink-0 text-right font-mono text-xs font-medium tabular-nums",
        percent === undefined ? "text-ink-400" : "text-ink-500",
      )}
    >
      {percent === undefined
        ? t("weights.shareUnavailable")
        : t("weights.share", { percent })}
    </p>
  );
}

function displayWeight(value: number | undefined): string {
  return isValidWeight(value) ? String(value) : "";
}
