import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfigChangeConfirmDialog } from "./config-change-confirm-dialog";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

describe("ConfigChangeConfirmDialog", () => {
  it("shows before/after values and confirms explicitly", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfigChangeConfirmDialog
        open
        onOpenChange={() => {}}
        changes={[{ label: "Capacity", before: "1 GiB", after: "512 MiB" }]}
        impact="New writes may be rejected."
        onConfirm={onConfirm}
      />,
    );

    expect(screen.getByText("1 GiB")).toBeVisible();
    expect(screen.getByText("512 MiB")).toBeVisible();
    expect(screen.getByText("New writes may be rejected.")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "confirm" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
