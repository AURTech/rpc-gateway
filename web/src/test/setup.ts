import "@testing-library/jest-dom/vitest";
import { MotionGlobalConfig } from "motion/react";

// jsdom has no real animation clock; make motion (AnimatePresence enter/exit)
// resolve instantly so mount/unmount is synchronous in tests.
MotionGlobalConfig.skipAnimations = true;

/**
 * jsdom doesn't implement `matchMedia`, which `useMediaQuery` / `useIsDesktop`
 * (src/hooks/use-media-query.ts) call. Default to a desktop match
 * (`(min-width: 48rem)` → true) so responsive components render their desktop
 * branch (e.g. the gateways table) in tests. A test that needs the mobile
 * branch can override `window.matchMedia` for its scope and restore it after.
 */
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => {
    const matches = /min-width/.test(query);
    return {
      matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    } as MediaQueryList;
  };
}

/**
 * jsdom doesn't implement `IntersectionObserver`, which the mobile list's
 * scroll-loading (src/hooks/use-infinite-scroll.ts) uses. Stub a no-op so the
 * observer is created but never fires — the mobile list renders without
 * auto-fetching the next page in tests.
 */
if (
  typeof globalThis !== "undefined" &&
  !("IntersectionObserver" in globalThis)
) {
  class IntersectionObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
    root = null;
    rootMargin = "";
    thresholds = [];
  }
  globalThis.IntersectionObserver =
    IntersectionObserverStub as unknown as typeof IntersectionObserver;
}

/**
 * jsdom doesn't implement `ResizeObserver`, which Radix primitives that measure
 * a node (e.g. the Switch thumb via `react-use-size`) construct in a layout
 * effect. Stub a no-op so those components mount instead of throwing.
 */
if (typeof globalThis !== "undefined" && !("ResizeObserver" in globalThis)) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver;
}

/**
 * jsdom implements neither the pointer capture APIs nor `scrollIntoView`, both
 * of which Radix Select calls while opening: it captures the pointer on the
 * trigger and scrolls the active item into view. Without these the combobox
 * throws instead of opening, so every test that picks a network, gateway or
 * protocol from a Select needs them.
 */
if (typeof Element !== "undefined") {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
}
