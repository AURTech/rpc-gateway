import { Skeleton } from "@/components/ui/skeleton";

/**
 * Suspense fallback for dashboard route changes.
 *
 * It lives here rather than at `[locale]/loading.tsx` on purpose: that boundary
 * sits *above* `dashboard/layout.tsx`, so its fallback replaces the whole shell
 * — sidebar included — and a page-shaped skeleton there would flash a
 * layout that has no navigation. Nested here, only the content area swaps while
 * the sidebar stays put.
 *
 * The shape deliberately matches the header rhythm every dashboard page shares
 * (`gap-7 pt-2`, a title over a subhead, then a content block), so the arrival
 * animation in `PageTransition` has something to hand off to instead of a
 * blank viewport.
 */
export default function DashboardLoading() {
  return (
    <div className="flex flex-col gap-7 pt-2">
      <header className="flex flex-col gap-1.5">
        <Skeleton className="h-9 w-56" />
        <Skeleton className="h-6 w-full max-w-prose-narrow" />
      </header>
      <Skeleton className="h-96 w-full rounded-3xl" />
    </div>
  );
}
