import type * as React from "react";
import type { RpcProviderVendor } from "@/api/providers/client";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

/**
 * Per-vendor brand identity: the primary brand color (used for the tile and the
 * card accent), a monogram fallback, and — for vendors we ship a bundled mark
 * for — a white logo glyph under `public/providers/<vendor>.svg`. Vendors
 * without a usable square mark fall back to the monogram automatically.
 */
export const VENDOR_BRAND: Record<
  RpcProviderVendor,
  { color: string; initial: string; hasLogo: boolean; hasCover: boolean }
> = {
  alchemy: { color: "#363FF9", initial: "A", hasLogo: false, hasCover: false },
  quicknode: {
    color: "#0A65FF",
    initial: "Q",
    hasLogo: false,
    hasCover: false,
  },
  chainstack: {
    color: "#007BFF",
    initial: "C",
    hasLogo: false,
    hasCover: false,
  },
  drpc: { color: "#2FB35A", initial: "D", hasLogo: false, hasCover: false },
  tenderly: { color: "#7C3AED", initial: "T", hasLogo: true, hasCover: false },
};

/**
 * Vendor logo as an {@link Avatar}: a brand-colored rounded tile carrying the
 * white logo glyph when we bundle one, and gracefully falling back to the
 * vendor's monogram (same tile) when the image is missing or fails to load.
 */
export function VendorLogo({
  vendor,
  label,
  className,
}: {
  vendor: RpcProviderVendor;
  label: string;
  className?: string;
}) {
  const brand = VENDOR_BRAND[vendor];
  return (
    <Avatar
      className={cn("rounded-full", className)}
      style={{ backgroundColor: brand.color }}
    >
      {brand.hasLogo ? (
        <AvatarImage src={`/providers/${vendor}.svg`} alt={label} />
      ) : null}
      <AvatarFallback className="rounded-full bg-transparent font-semibold text-white">
        {brand.initial}
      </AvatarFallback>
    </Avatar>
  );
}

/**
 * Card cover band for a vendor: a brand-colored gradient wash with a faint
 * geometric overlay, used as the banner behind the overlapping logo. When a
 * generated cover image is bundled (`hasCover`) it renders on top via
 * `public/providers/covers/<vendor>.png`; otherwise the branded gradient stands
 * in on its own. Purely decorative.
 */
export function VendorCover({
  vendor,
  className,
  style,
}: {
  vendor: RpcProviderVendor;
  className?: string;
  style?: React.CSSProperties;
}) {
  const brand = VENDOR_BRAND[vendor];
  return (
    <div
      aria-hidden
      className={cn("relative overflow-hidden", className)}
      style={{
        ...style,
        backgroundImage: `linear-gradient(135deg, ${brand.color} 0%, ${brand.color}b3 55%, ${brand.color}66 100%)`,
      }}
    >
      {/* Faint dotted texture so the band reads as a designed cover, not a flat fill. */}
      <div
        className="absolute inset-0 opacity-25 mix-blend-soft-light"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.9) 1px, transparent 1.4px)",
          backgroundSize: "12px 12px",
        }}
      />
      {brand.hasCover ? (
        // biome-ignore lint/performance/noImgElement: static, bundled cover in /public; next/image would add config and an optimizer hop for no benefit.
        <img
          src={`/providers/covers/${vendor}.png`}
          alt=""
          loading="lazy"
          decoding="async"
          className="absolute inset-0 size-full object-cover"
        />
      ) : null}
    </div>
  );
}
