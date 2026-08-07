import { afterEach, describe, expect, it, vi } from "vitest";

import { okResponse } from "@/test/fetch";

import {
  createPersonalAccessToken,
  listPersonalAccessTokens,
  revokePersonalAccessToken,
} from "./client";

afterEach(() => vi.restoreAllMocks());

describe("personal access token client", () => {
  it("lists token metadata without requiring a secret", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okResponse({
        page: 1,
        size: 20,
        total: 1,
        max_page: 1,
        active: 1,
        max_active: 20,
        items: [
          {
            id: "token-1",
            name: "Codex",
            token_prefix: "rg_pat_example",
            scopes: ["overview:read"],
            state: "active",
            expires_at: "2026-11-01T00:00:00Z",
            last_used_at: null,
            revoked_at: null,
            created_at: "2026-08-03T00:00:00Z",
          },
        ],
      }),
    );

    const result = await listPersonalAccessTokens();
    expect(result.items[0]).not.toHaveProperty("token");
    expect(result).toMatchObject({ total: 1, active: 1, maxActive: 20 });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/size=20.*state=active/),
      expect.anything(),
    );
  });

  it("creates a scoped token and returns the one-time secret", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okResponse({
        id: "token-1",
        name: "Codex",
        token_prefix: "rg_pat_example",
        token: "rg_pat_example-secret",
        scopes: ["overview:read"],
        state: "active",
        expires_at: "2026-11-01T00:00:00Z",
        last_used_at: null,
        revoked_at: null,
        created_at: "2026-08-03T00:00:00Z",
      }),
    );

    const result = await createPersonalAccessToken({
      name: "Codex",
      scopes: ["overview:read"],
    });
    expect(result.token).toBe("rg_pat_example-secret");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v2/auth/personal-access-tokens"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("revokes a token with DELETE", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      okResponse({
        id: "token-1",
        revoked: true,
        revoked_at: "2026-08-03T00:00:00Z",
      }),
    );

    await revokePersonalAccessToken("token-1");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v2/auth/personal-access-tokens/token-1"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
