import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CompactTablePager } from "./compact-table-pager";

const baseProps = {
  page: 2,
  maxPage: 4,
  pageSize: 5,
  pageItemCount: 5,
  total: 18,
  rangeLabel: ({
    from,
    to,
    total,
  }: {
    from: number;
    to: number;
    total: number;
  }) => `${from}–${to} of ${total}`,
  prevLabel: "Previous page",
  nextLabel: "Next page",
};

describe("CompactTablePager", () => {
  it("shows the active range and moves one page at a time", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    render(<CompactTablePager {...baseProps} onPageChange={onPageChange} />);

    expect(screen.getByText("6–10 of 18")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Previous page" }));
    await user.click(screen.getByRole("button", { name: "Next page" }));

    expect(onPageChange).toHaveBeenNthCalledWith(1, 1);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 3);
  });

  it("disables boundary and loading actions", () => {
    const { rerender } = render(
      <CompactTablePager {...baseProps} page={1} onPageChange={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: "Previous page" }),
    ).toBeDisabled();

    rerender(
      <CompactTablePager {...baseProps} loading onPageChange={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: "Previous page" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("uses the actual item count on the final page", () => {
    render(
      <CompactTablePager
        {...baseProps}
        page={4}
        pageItemCount={3}
        onPageChange={vi.fn()}
      />,
    );

    expect(screen.getByText("16–18 of 18")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("reports an empty page without a misleading offset", () => {
    render(
      <CompactTablePager
        {...baseProps}
        pageItemCount={0}
        total={0}
        onPageChange={vi.fn()}
      />,
    );

    expect(screen.getByText("0–0 of 0")).toBeInTheDocument();
  });
});
