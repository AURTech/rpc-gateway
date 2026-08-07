import { describe, expect, it } from "vitest";

import { loadMessages } from "./messages";

/** Collect every leaf key path (dot-joined) of a nested message bag. */
function leafPaths(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return [prefix];
  }
  return Object.entries(value as Record<string, unknown>).flatMap(([key, v]) =>
    leafPaths(v, prefix ? `${prefix}.${key}` : key),
  );
}

function get(bag: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (acc, key) =>
        typeof acc === "object" && acc !== null
          ? (acc as Record<string, unknown>)[key]
          : undefined,
      bag,
    );
}

describe("i18n message contract", () => {
  it("loads every English message namespace", async () => {
    const messages = await loadMessages();

    expect(leafPaths(messages)).toContain("dashboard.endpoints.fields.name");
    expect(get(messages, "dashboard.endpoints.fields.name")).toBe("Name");
  });
});
