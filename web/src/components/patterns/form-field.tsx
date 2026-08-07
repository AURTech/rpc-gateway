import {
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type FieldProps = {
  /** Field label text. Omit for a control that labels itself. */
  label?: ReactNode;
  /** Associates the label with the control. */
  htmlFor?: string;
  /** Helper text shown below the control when there is no error. */
  hint?: ReactNode;
  /** Validation message; replaces the hint and tints it as an error. */
  error?: ReactNode;
  required?: boolean;
  className?: string;
  labelClassName?: string;
  /** The form control (input, select, textarea, …). */
  children: ReactNode;
};

/**
 * Presentational form field: label + control + hint/error. Deliberately free
 * of react-hook-form so existing `useState`-driven dialogs can adopt it without
 * changing their state management. For RHF-backed forms, compose the `ui/form`
 * primitives instead.
 */
export function Field({
  label,
  htmlFor,
  hint,
  error,
  required = false,
  className,
  labelClassName,
  children,
}: FieldProps) {
  const messageId =
    htmlFor && (error || hint)
      ? `${htmlFor}-${error ? "error" : "hint"}`
      : undefined;
  const child = children as ReactElement<{ "aria-describedby"?: string }>;
  const describedChild =
    messageId && isValidElement(children)
      ? cloneElement(child, {
          "aria-describedby": [child.props["aria-describedby"], messageId]
            .filter(Boolean)
            .join(" "),
        })
      : children;

  return (
    <div data-slot="field" className={cn("flex flex-col gap-2", className)}>
      {label ? (
        <Label variant="field" htmlFor={htmlFor} className={labelClassName}>
          {label}
          {required ? (
            <span aria-hidden className="text-danger">
              {" *"}
            </span>
          ) : null}
        </Label>
      ) : null}
      {describedChild}
      {error ? (
        <p
          id={messageId}
          data-slot="field-error"
          className="text-sm text-danger"
        >
          {error}
        </p>
      ) : hint ? (
        <p
          id={messageId}
          data-slot="field-hint"
          className="text-sm text-ink-500"
        >
          {hint}
        </p>
      ) : null}
    </div>
  );
}
