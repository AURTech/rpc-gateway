import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Tabs } from "./tabs";

type V = "a" | "b" | "c";

const OPTIONS = [
  { value: "a" as const, label: "Alpha" },
  { value: "b" as const, label: "Beta" },
  { value: "c" as const, label: "Gamma" },
];

// Render the controlled Tabs inside a stateful wrapper so selection actually
// moves on click/keyboard (roving tabindex + aria state follow the live value),
// mirroring real usage.
function setup({
  mode,
  initial = "a",
  idBase,
  disabled,
}: {
  mode: "tab" | "segmented";
  initial?: V;
  idBase?: string;
  disabled?: boolean;
}) {
  const onChange = vi.fn();
  const user = userEvent.setup();

  function Wrapper() {
    const [value, setValue] = useState<V>(initial);
    return (
      <Tabs
        mode={mode}
        idBase={idBase}
        disabled={disabled}
        value={value}
        onChange={(next) => {
          setValue(next);
          onChange(next);
        }}
        options={OPTIONS}
        ariaLabel="Test switcher"
      />
    );
  }

  render(<Wrapper />);
  return { onChange, user };
}

describe("Tabs — segmented mode", () => {
  it("renders a radiogroup of radios with the active one checked", () => {
    setup({ mode: "segmented", initial: "b" });

    expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    expect(screen.getByRole("radio", { name: "Beta" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("radio", { name: "Alpha" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });
});

describe("Tabs — tab mode", () => {
  it("renders a tablist of tabs with the active one selected", () => {
    setup({ mode: "tab", initial: "a" });

    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("tab", { name: "Alpha" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("wires aria-controls to a panel id when idBase is given", () => {
    setup({ mode: "tab", initial: "a", idBase: "usage-tab" });

    const tab = screen.getByRole("tab", { name: "Alpha" });
    expect(tab).toHaveAttribute("id", "usage-tab-a");
    expect(tab).toHaveAttribute("aria-controls", "usage-tab-panel");
  });
});

describe("Tabs — pointer", () => {
  it("calls onChange with the clicked option's value", async () => {
    const { onChange, user } = setup({ mode: "segmented", initial: "a" });

    await user.click(screen.getByRole("radio", { name: "Gamma" }));

    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("disables every option and ignores clicks when disabled", async () => {
    const { onChange, user } = setup({
      mode: "segmented",
      initial: "a",
      disabled: true,
    });

    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toBeDisabled();
    }
    await user.click(screen.getByRole("radio", { name: "Gamma" }));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("Tabs — keyboard (roving tabindex + arrows)", () => {
  it("gives the active option tabindex 0 and the rest -1", () => {
    setup({ mode: "tab", initial: "b" });

    expect(screen.getByRole("tab", { name: "Beta" })).toHaveAttribute(
      "tabindex",
      "0",
    );
    expect(screen.getByRole("tab", { name: "Alpha" })).toHaveAttribute(
      "tabindex",
      "-1",
    );
  });

  it("ArrowRight moves to and activates the next option", async () => {
    const { onChange, user } = setup({ mode: "tab", initial: "a" });

    screen.getByRole("tab", { name: "Alpha" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenCalledWith("b");
    expect(screen.getByRole("tab", { name: "Beta" })).toHaveFocus();
  });

  it("ArrowRight wraps from the last option to the first", async () => {
    const { onChange, user } = setup({ mode: "tab", initial: "c" });

    screen.getByRole("tab", { name: "Gamma" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenCalledWith("a");
    expect(screen.getByRole("tab", { name: "Alpha" })).toHaveFocus();
  });

  it("ArrowLeft wraps from the first option to the last", async () => {
    const { onChange, user } = setup({ mode: "tab", initial: "a" });

    screen.getByRole("tab", { name: "Alpha" }).focus();
    await user.keyboard("{ArrowLeft}");

    expect(onChange).toHaveBeenCalledWith("c");
    expect(screen.getByRole("tab", { name: "Gamma" })).toHaveFocus();
  });

  it("Home jumps to the first and End to the last option", async () => {
    const { onChange, user } = setup({ mode: "tab", initial: "b" });

    screen.getByRole("tab", { name: "Beta" }).focus();
    await user.keyboard("{Home}");
    expect(onChange).toHaveBeenCalledWith("a");
    expect(screen.getByRole("tab", { name: "Alpha" })).toHaveFocus();

    await user.keyboard("{End}");
    expect(onChange).toHaveBeenCalledWith("c");
    expect(screen.getByRole("tab", { name: "Gamma" })).toHaveFocus();
  });
});
