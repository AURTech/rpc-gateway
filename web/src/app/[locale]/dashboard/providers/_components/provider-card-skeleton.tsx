import { Skeleton } from "@/components/ui/skeleton";

/**
 * Loading placeholder mirroring {@link ProviderCard}'s banner anatomy: cover
 * band, circular logo straddling its bottom edge, name block, meta chips, and
 * the footer status row — so the grid doesn't reflow when real cards arrive.
 */
export function ProviderCardSkeleton() {
  return (
    <div
      aria-busy="true"
      className="flex flex-col overflow-hidden rounded-2xl bg-surface shadow-card"
    >
      <div className="relative">
        <Skeleton
          className="w-full rounded-none"
          style={{ aspectRatio: "16 / 6" }}
        />
        <Skeleton className="absolute left-4 top-full size-14 -translate-y-1/2 rounded-full ring-2 ring-surface" />
      </div>

      <div className="flex flex-col gap-3 p-4 pt-9">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <Skeleton className="h-5 w-16 shrink-0 rounded-full" />
        </div>

        <div className="flex flex-wrap gap-1.5">
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-5 w-24 rounded-full" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-table-frame pt-3">
          <Skeleton className="h-3 w-2/5" />
          <Skeleton className="size-8 shrink-0 rounded-md" />
        </div>
      </div>
    </div>
  );
}
