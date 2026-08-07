"use client";

import type { RpcProviderVendor } from "@/api/providers/client";
import { cn } from "@/lib/utils";

import { VendorLogo } from "./provider-brand";

/**
 * Brand-forward multi-select vendor filter: one chip per vendor carrying the
 * vendor's circular logo, plus a leading "all vendors" chip that clears the
 * selection. Empty `value` means "all". Shares the filter-drawer chip visual
 * language (sunken ink-wash rest state, brand-soft when selected) so it reads
 * as a control, not a floating card.
 */

const CHIP_BASE =
  "inline-flex items-center rounded-full font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40";

function chipClass(on: boolean) {
  return cn(
    CHIP_BASE,
    "h-9 gap-2 px-3.5 text-sm",
    on
      ? "bg-brand-soft text-brand"
      : "bg-ink-wash text-ink-700 hover:bg-stripe",
  );
}

export function VendorFilterChips({
  options,
  optionLabels,
  allLabel,
  value,
  onValueChange,
}: {
  options: readonly RpcProviderVendor[];
  optionLabels: Record<RpcProviderVendor, string>;
  allLabel: string;
  value: readonly RpcProviderVendor[];
  onValueChange: (next: readonly RpcProviderVendor[]) => void;
}) {
  const selected = new Set(value);
  const allOn = value.length === 0;

  const toggle = (vendor: RpcProviderVendor) => {
    if (selected.has(vendor)) onValueChange(value.filter((v) => v !== vendor));
    else onValueChange([...value, vendor]);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        aria-pressed={allOn}
        onClick={() => {
          if (!allOn) onValueChange([]);
        }}
        className={chipClass(allOn)}
      >
        {allLabel}
      </button>
      {options.map((vendor) => {
        const on = selected.has(vendor);
        return (
          <button
            key={vendor}
            type="button"
            aria-pressed={on}
            onClick={() => toggle(vendor)}
            className={chipClass(on)}
          >
            <VendorLogo
              vendor={vendor}
              label={optionLabels[vendor]}
              className={cn("size-5 shrink-0", !on && "opacity-80")}
            />
            {optionLabels[vendor]}
          </button>
        );
      })}
    </div>
  );
}
