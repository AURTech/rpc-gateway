import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Time } from "./time";

describe("Time", () => {
  it("renders a semantic <time> with ISO datetime, display text, and full-precision title", () => {
    const { container } = render(<Time value="2026-06-29T14:32:05.000Z" />);
    const el = container.querySelector("time");

    expect(el).not.toBeNull();
    expect(el).toHaveAttribute("datetime", "2026-06-29T14:32:05.000Z");
    expect(el).toHaveAttribute("title", "2026-06-29 14:32:05 UTC");
    expect(el).toHaveTextContent("2026-06-29 14:32");
    expect(el).toHaveClass("tabular-nums");
  });

  it("falls back to an em dash and no <time> element when value is missing", () => {
    const { container } = render(<Time value={null} />);

    expect(container.querySelector("time")).toBeNull();
    expect(container.textContent).toBe("—");
  });

  it("renders an unparseable value verbatim without a <time> element", () => {
    const { container } = render(<Time value="whenever" />);

    expect(container.querySelector("time")).toBeNull();
    expect(container.textContent).toBe("whenever");
  });

  it("applies the monospaced look when `mono` is set", () => {
    const { container } = render(
      <Time value="2026-06-29T14:32:05.000Z" mono />,
    );

    expect(container.querySelector("time")).toHaveClass("font-mono");
  });
});
