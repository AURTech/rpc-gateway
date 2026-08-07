import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Stepper } from "./stepper";

function renderStepper(currentStep: number, orientation?: "vertical") {
  return render(
    <Stepper currentStep={currentStep} orientation={orientation}>
      {["Project", "Networks", "Done"].map((label) => (
        <Stepper.Step key={label}>
          <Stepper.Indicator />
          <Stepper.Content>
            <Stepper.Title>{label}</Stepper.Title>
          </Stepper.Content>
          <Stepper.Separator />
        </Stepper.Step>
      ))}
    </Stepper>,
  );
}

describe("Stepper", () => {
  it("marks past steps complete, the current step active, and later steps inactive", () => {
    const { container } = renderStepper(1);
    const steps = container.querySelectorAll('[data-slot="stepper-step"]');

    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveAttribute("data-status", "complete");
    expect(steps[1]).toHaveAttribute("data-status", "active");
    expect(steps[2]).toHaveAttribute("data-status", "inactive");
  });

  it("replaces the number with a checkmark once a step is complete", () => {
    renderStepper(1);

    // Step 1's number (1) becomes a checkmark; the later steps keep numbers.
    expect(screen.queryByText("1")).not.toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders every step title", () => {
    renderStepper(1);

    expect(screen.getByText("Project")).toBeInTheDocument();
    expect(screen.getByText("Networks")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("hides the separator on the last step", () => {
    const { container } = renderStepper(0);

    // Three steps → separators only after the first two.
    expect(
      container.querySelectorAll('[data-slot="stepper-separator"]'),
    ).toHaveLength(2);
  });

  it("exposes the orientation on the root", () => {
    const { container } = renderStepper(0, "vertical");

    expect(container.querySelector('[data-slot="stepper"]')).toHaveAttribute(
      "data-orientation",
      "vertical",
    );
  });
});
