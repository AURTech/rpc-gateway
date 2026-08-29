import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FieldMessage } from "./field-message";
import { Field } from "./form-field";

describe("FieldMessage", () => {
  it("keeps the id and slot on the paragraph itself", () => {
    // `aria-describedby` points at the id and the field tests query the slot,
    // so neither may move onto the animating wrapper.
    const { container } = render(
      <FieldMessage
        messageKey="hint"
        id="field-1-message"
        slot="field-hint"
        className="text-sm"
      >
        Shown to your team.
      </FieldMessage>,
    );

    const message = container.querySelector('[data-slot="field-hint"]');
    expect(message?.tagName).toBe("P");
    expect(message).toHaveAttribute("id", "field-1-message");
  });
});

describe("Field messages", () => {
  it("still wires aria-describedby to the rendered message", () => {
    render(
      <Field label="Slug" htmlFor="slug" error="Slug is already taken.">
        <input id="slug" />
      </Field>,
    );

    const input = screen.getByLabelText("Slug");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)?.textContent).toBe(
      "Slug is already taken.",
    );
  });

  it("swaps a hint for an error", async () => {
    const { rerender } = render(
      <Field label="Slug" htmlFor="slug" hint="Lowercase only.">
        <input id="slug" />
      </Field>,
    );
    expect(screen.getByText("Lowercase only.")).toBeInTheDocument();

    rerender(
      <Field label="Slug" htmlFor="slug" error="Slug is already taken.">
        <input id="slug" />
      </Field>,
    );

    // mode="wait" holds the outgoing message for a frame, so the swap is not
    // observable synchronously even with MotionGlobalConfig.skipAnimations.
    expect(
      await screen.findByText("Slug is already taken."),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText("Lowercase only.")).not.toBeInTheDocument(),
    );
  });
});
