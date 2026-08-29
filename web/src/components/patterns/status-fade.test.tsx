import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusFade } from "./status-fade";

describe("StatusFade", () => {
  it("renders its children under a status-fade slot", () => {
    const { container } = render(<StatusFade>Nothing here yet</StatusFade>);

    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
    expect(container.querySelector('[data-slot="status-fade"]')).not.toBeNull();
  });

  it("absorbs the panel's own element rather than nesting inside it", () => {
    // card-grid-view and mobile-data-list hand it the wrapper classes and the
    // alert role directly; an extra level would detach the layout and the role.
    const { container } = render(
      <StatusFade role="alert" className="py-14 text-center">
        Could not load providers
      </StatusFade>,
    );

    const node = container.querySelector('[data-slot="status-fade"]');
    expect(node).toHaveClass("py-14", "text-center");
    expect(node).toHaveAttribute("role", "alert");
    expect(screen.getByRole("alert")).toBe(node);
  });
});
