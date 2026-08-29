import { describe, expect, it } from "vitest";

import common from "../locales/en/common.json";
import { messages } from "./messages";

const PAGE_NAMESPACES = ["auth", "dashboard"] as const;

describe("i18n message bag", () => {
  it("exposes every page namespace alongside the common keys", () => {
    for (const namespace of PAGE_NAMESPACES) {
      expect(messages[namespace]).toBeTypeOf("object");
    }
    expect(messages.errors).toBe(common.errors);
  });

  it("keeps common.json free of keys that would shadow a page namespace", () => {
    // `common` is spread at the root of the bag, so a `common.json` key named
    // after a page bundle would be silently replaced by that bundle.
    const collisions = PAGE_NAMESPACES.filter(
      (namespace) => namespace in common,
    );

    expect(collisions).toEqual([]);
  });
});
