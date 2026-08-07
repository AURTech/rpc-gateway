import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Input } from "@/components/ui/input";

import { Field } from "./form-field";

describe("Field", () => {
  it("connects hint text to its control", () => {
    render(
      <Field label="Name" htmlFor="name" hint="Shown to operators">
        <Input id="name" />
      </Field>,
    );

    expect(screen.getByLabelText("Name")).toHaveAttribute(
      "aria-describedby",
      "name-hint",
    );
    expect(screen.getByText("Shown to operators")).toHaveAttribute(
      "id",
      "name-hint",
    );
  });

  it("connects validation errors while preserving existing descriptions", () => {
    render(
      <Field label="Limit" htmlFor="limit" error="Out of range">
        <Input id="limit" aria-describedby="limit-help" />
      </Field>,
    );

    expect(screen.getByLabelText("Limit")).toHaveAttribute(
      "aria-describedby",
      "limit-help limit-error",
    );
  });
});
