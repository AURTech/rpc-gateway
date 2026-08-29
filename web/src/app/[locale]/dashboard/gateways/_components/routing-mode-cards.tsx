"use client";

import {
  CheckIcon,
  ListOrderedIcon,
  type LucideIcon,
  ShuffleIcon,
} from "lucide-react";
import { useId } from "react";

import type { JsonRpcStrategyType } from "@/api/jsonrpc-routes/client";
import { cn } from "@/lib/utils";

type RoutingModeCardOption = {
  value: JsonRpcStrategyType;
  label: string;
  hint: string;
};

const MODE_ICONS: Record<JsonRpcStrategyType, LucideIcon> = {
  priority_failover: ListOrderedIcon,
  load_balance: ShuffleIcon,
};

export function RoutingModeCards({
  value,
  onChange,
  options,
  ariaLabel,
  disabled = false,
}: {
  value: JsonRpcStrategyType;
  onChange: (next: JsonRpcStrategyType) => void;
  options: readonly RoutingModeCardOption[];
  ariaLabel: string;
  disabled?: boolean;
}) {
  const name = useId();

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="grid gap-3 sm:grid-cols-2"
    >
      {options.map((option) => {
        const active = option.value === value;
        const Icon = MODE_ICONS[option.value];
        return (
          <label key={option.value} className="block min-w-0">
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={active}
              disabled={disabled}
              onChange={() => onChange(option.value)}
              aria-label={option.label}
              className="peer sr-only"
            />
            <span
              className={cn(
                "flex min-h-32 cursor-pointer flex-col gap-4 rounded-xl bg-ink-wash px-4 py-4 text-left transition-colors",
                "peer-focus-visible:ring-2 peer-focus-visible:ring-brand/30",
                active
                  ? "bg-brand-soft text-brand"
                  : "text-ink-700 hover:bg-stripe",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <span className="flex items-start justify-between gap-3">
                <span
                  className={cn(
                    "inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-surface",
                    active ? "text-brand" : "text-ink-500",
                  )}
                  aria-hidden
                >
                  <Icon className="size-4" />
                </span>
                {active ? (
                  <span
                    className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-brand text-white"
                    aria-hidden
                  >
                    <CheckIcon className="size-3" />
                  </span>
                ) : null}
              </span>
              <span className="flex flex-1 flex-col gap-1">
                <span className="text-sm font-semibold text-ink-900">
                  {option.label}
                </span>
                <span className="text-sm leading-5 text-ink-500">
                  {option.hint}
                </span>
              </span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
