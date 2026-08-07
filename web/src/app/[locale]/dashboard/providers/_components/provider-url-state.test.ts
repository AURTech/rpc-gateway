import { afterEach, describe, expect, it } from "vitest";

import { replaceProviderSearchParam } from "./provider-url-state";

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("replaceProviderSearchParam", () => {
  it("adds the provider while preserving the rest of the URL", () => {
    window.history.replaceState(
      { marker: "current-entry" },
      "",
      "/en/dashboard/providers?source=endpoints#list",
    );

    replaceProviderSearchParam("provider / 1");

    expect(window.location.pathname).toBe("/en/dashboard/providers");
    expect(window.location.search).toBe(
      "?source=endpoints&provider=provider+%2F+1",
    );
    expect(window.location.hash).toBe("#list");
    expect(window.history.state).toEqual({ marker: "current-entry" });
  });

  it("removes only the provider parameter", () => {
    window.history.replaceState(
      null,
      "",
      "/en/dashboard/providers?provider=prov_1&source=endpoints#list",
    );

    replaceProviderSearchParam(null);

    expect(window.location.href).toBe(
      "http://localhost:3000/en/dashboard/providers?source=endpoints#list",
    );
  });
});
