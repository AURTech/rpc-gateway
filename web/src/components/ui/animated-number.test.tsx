import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnimatedNumber } from "./animated-number";

const compact = (value: number) => `${Math.round(value).toLocaleString()} req`;

describe("AnimatedNumber", () => {
  it("settles on the formatted target value", async () => {
    render(<AnimatedNumber value={1234} format={compact} />);

    // MotionGlobalConfig.skipAnimations (src/test/setup.ts) resolves the tween
    // immediately, so this asserts the landing value rather than the travel.
    await waitFor(() =>
      expect(screen.getByText("1,234 req")).toBeInTheDocument(),
    );
  });

  it("re-targets when the value changes", async () => {
    const { rerender } = render(<AnimatedNumber value={10} format={compact} />);
    await waitFor(() => expect(screen.getByText("10 req")).toBeInTheDocument());

    rerender(<AnimatedNumber value={99} format={compact} />);

    await waitFor(() => expect(screen.getByText("99 req")).toBeInTheDocument());
  });

  it("runs every frame through the formatter", async () => {
    const format = vi.fn(compact);
    render(<AnimatedNumber value={42} format={format} />);

    await waitFor(() => expect(screen.getByText("42 req")).toBeInTheDocument());
    // A raw count would flicker unformatted text mid-tween.
    expect(format).toHaveBeenCalled();
  });

  it("carries the animated-number slot", () => {
    const { container } = render(<AnimatedNumber value={1} format={compact} />);

    expect(
      container.querySelector('[data-slot="animated-number"]'),
    ).not.toBeNull();
  });
});
