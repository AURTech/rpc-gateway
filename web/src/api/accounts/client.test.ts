import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";

import { updateAccountStatus } from "./client";

const accountFixture = {
  id: "acct_1",
  email: "member@example.com",
  role: "user",
  status: "disabled",
  name: null,
  avatar_url: null,
  created_at: "2026-03-14T00:00:00Z",
  modified_at: "2026-05-14T00:00:00Z",
  role_label: "User",
  status_label: "Disabled",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("accounts client", () => {
  it("updateAccountStatus POSTs the update endpoint", async () => {
    const spy = vi.spyOn(api, "post").mockResolvedValue({
      msg: "ok",
      data: accountFixture,
    });

    const updated = await updateAccountStatus("acct_1", {
      status: "disabled",
    });

    expect(spy).toHaveBeenCalledWith("/v2/accounts/acct_1", {
      status: "disabled",
    });
    expect(updated.status).toBe("disabled");
  });
});
