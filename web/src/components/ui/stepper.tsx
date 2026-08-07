"use client";

import { CheckIcon } from "lucide-react";
import {
  Children,
  type ComponentProps,
  createContext,
  isValidElement,
  type ReactNode,
  useContext,
  useState,
} from "react";

import { cn } from "@/lib/utils";

/**
 * Compositional step-progress indicator, modelled on the HeroUI Stepper effect
 * but built on the project's design tokens (no external dependency). Access the
 * parts with dot notation:
 *
 * ```tsx
 * <Stepper currentStep={1}>
 *   <Stepper.Step>
 *     <Stepper.Indicator />
 *     <Stepper.Content>
 *       <Stepper.Title>Project</Stepper.Title>
 *       <Stepper.Description>Name your app</Stepper.Description>
 *     </Stepper.Content>
 *     <Stepper.Separator />
 *   </Stepper.Step>
 *   …
 * </Stepper>
 * ```
 *
 * Each step derives its status (`inactive` | `active` | `complete`) from
 * `currentStep`: indices before it are complete, the index itself is active.
 * `Stepper.Step` reorders its children internally, so the indicator, content,
 * and separator lay out correctly in both orientations regardless of the order
 * you write them.
 */

type Orientation = "horizontal" | "vertical";
type StepperSize = "sm" | "md" | "lg";
type StepStatus = "inactive" | "active" | "complete";

type StepperContextValue = {
  currentStep: number;
  orientation: Orientation;
  size: StepperSize;
  onStepChange?: (step: number) => void;
};

type StepContextValue = {
  index: number;
  status: StepStatus;
  isLast: boolean;
};

const StepperContext = createContext<StepperContextValue | null>(null);
const StepContext = createContext<StepContextValue | null>(null);

function useStepper(): StepperContextValue {
  const ctx = useContext(StepperContext);
  if (!ctx) throw new Error("Stepper parts must be used within <Stepper>");
  return ctx;
}

/** Per-step context for any descendant of {@link Stepper.Step}. */
export function useStepperStep(): StepContextValue {
  const ctx = useContext(StepContext);
  if (!ctx)
    throw new Error("useStepperStep must be used within <Stepper.Step>");
  return ctx;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function statusFor(index: number, current: number): StepStatus {
  if (index < current) return "complete";
  if (index === current) return "active";
  return "inactive";
}

type StepperProps = Omit<ComponentProps<"ol">, "children"> & {
  /** Active step index (controlled). Falls back to the uncontrolled value. */
  currentStep?: number;
  /** Initial step index when uncontrolled. */
  defaultStep?: number;
  /** Fires when a step is activated; presence makes steps interactive. */
  onStepChange?: (step: number) => void;
  orientation?: Orientation;
  size?: StepperSize;
  children?: ReactNode;
};

function StepperRoot({
  currentStep,
  defaultStep = 0,
  onStepChange,
  orientation = "horizontal",
  size = "md",
  className,
  children,
  ...rest
}: StepperProps) {
  const [internal, setInternal] = useState(defaultStep);
  const current = currentStep ?? internal;

  const handleStepChange = onStepChange
    ? (step: number) => {
        if (currentStep === undefined) setInternal(step);
        onStepChange(step);
      }
    : undefined;

  const steps = Children.toArray(children).filter(isValidElement);
  const count = steps.length;

  return (
    <StepperContext.Provider
      value={{
        currentStep: current,
        orientation,
        size,
        onStepChange: handleStepChange,
      }}
    >
      <ol
        data-slot="stepper"
        data-orientation={orientation}
        className={cn(
          "flex",
          orientation === "horizontal" ? "w-full items-center" : "flex-col",
          className,
        )}
        {...rest}
      >
        {steps.map((child, index) => (
          <StepContext.Provider
            // biome-ignore lint/suspicious/noArrayIndexKey: steps are a static, ordered list with no stable id.
            key={index}
            value={{
              index,
              status: statusFor(index, current),
              isLast: index === count - 1,
            }}
          >
            {child}
          </StepContext.Provider>
        ))}
      </ol>
    </StepperContext.Provider>
  );
}

function findChild(children: ReactNode, type: unknown): ReactNode {
  return Children.toArray(children).find(
    (child) => isValidElement(child) && child.type === type,
  );
}

function Step({ children, className, ...rest }: ComponentProps<"li">) {
  const { orientation, onStepChange } = useStepper();
  const { index, status, isLast } = useStepperStep();

  const indicator = findChild(children, Indicator);
  const separator = findChild(children, Separator);
  const content = Children.toArray(children).filter(
    (child) =>
      !(
        isValidElement(child) &&
        (child.type === Indicator || child.type === Separator)
      ),
  );

  const clickable = onStepChange !== undefined;
  const group = (
    <>
      {indicator}
      {content}
    </>
  );

  if (orientation === "vertical") {
    return (
      <li
        data-slot="stepper-step"
        data-status={status}
        className={cn("flex gap-3", className)}
        {...rest}
      >
        <div className="flex flex-col items-center self-stretch">
          {clickable ? (
            <button
              type="button"
              data-clickable
              onClick={() => onStepChange?.(index)}
              className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
            >
              {indicator}
            </button>
          ) : (
            indicator
          )}
          {!isLast ? separator : null}
        </div>
        <div className="flex flex-1 flex-col pb-6">{content}</div>
      </li>
    );
  }

  return (
    <li
      data-slot="stepper-step"
      data-status={status}
      className={cn(
        "flex items-center gap-3",
        isLast ? "flex-none" : "flex-1",
        className,
      )}
      {...rest}
    >
      {clickable ? (
        <button
          type="button"
          data-clickable
          onClick={() => onStepChange?.(index)}
          className="flex items-center gap-3 rounded-md outline-none transition-opacity hover:opacity-80 focus-visible:ring-2 focus-visible:ring-brand/40"
        >
          {group}
        </button>
      ) : (
        <div className="flex items-center gap-3">{group}</div>
      )}
      {!isLast ? separator : null}
    </li>
  );
}

const INDICATOR_SIZE: Record<StepperSize, string> = {
  sm: "size-6 text-xs",
  md: "size-7 text-sm",
  lg: "size-9 text-md",
};

const INDICATOR_STATUS: Record<StepStatus, string> = {
  inactive: "border-ink-400/30 bg-surface text-ink-400",
  active: "border-brand bg-surface text-brand",
  complete: "border-brand bg-brand text-white",
};

function Indicator({ children, className, ...rest }: ComponentProps<"span">) {
  const { size } = useStepper();
  const { index, status } = useStepperStep();

  return (
    <span
      data-slot="stepper-indicator"
      data-status={status}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full border-2 font-semibold transition-colors",
        INDICATOR_SIZE[size],
        INDICATOR_STATUS[status],
        className,
      )}
      {...rest}
    >
      {children ??
        (status === "complete" ? (
          <CheckIcon className="size-4" aria-hidden />
        ) : (
          index + 1
        ))}
    </span>
  );
}

function Content({ children, className, ...rest }: ComponentProps<"span">) {
  const { orientation } = useStepper();
  return (
    <span
      className={cn(
        "flex min-w-0 flex-col",
        orientation === "vertical" ? "gap-0.5" : "gap-0",
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}

function Title({ children, className, ...rest }: ComponentProps<"span">) {
  const { status } = useStepperStep();
  return (
    <span
      className={cn(
        "text-sm font-medium transition-colors",
        status === "inactive" ? "text-ink-400" : "text-ink-900",
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}

function Description({ children, className, ...rest }: ComponentProps<"span">) {
  return (
    <span className={cn("text-xs text-ink-500", className)} {...rest}>
      {children}
    </span>
  );
}

function Icon({ children, className, ...rest }: ComponentProps<"span">) {
  return (
    <span
      className={cn("inline-flex items-center justify-center", className)}
      {...rest}
    >
      {children}
    </span>
  );
}

type SeparatorProps = Omit<ComponentProps<"div">, "children"> & {
  /** Explicit fill 0–1. Auto-computed from `currentStep` when omitted. */
  progress?: number;
  /** Render even on the last step (normally hidden). */
  force?: boolean;
};

function Separator({
  progress,
  force = false,
  className,
  ...rest
}: SeparatorProps) {
  const { orientation, currentStep } = useStepper();
  const { index, isLast } = useStepperStep();

  if (isLast && !force) return null;

  const fill = clamp01(progress ?? currentStep - index);
  const complete = fill >= 1;

  if (orientation === "vertical") {
    return (
      <div
        data-slot="stepper-separator"
        data-complete={complete || undefined}
        className={cn(
          "relative my-1 w-0.5 flex-1 overflow-hidden rounded-full bg-ink-wash",
          className,
        )}
        {...rest}
      >
        <div
          className="absolute inset-x-0 top-0 h-full origin-top bg-brand transition-transform duration-500 ease-out"
          style={{ transform: `scaleY(${fill})` }}
        />
      </div>
    );
  }

  return (
    <div
      data-slot="stepper-separator"
      data-complete={complete || undefined}
      className={cn(
        "relative mx-2 h-0.5 flex-1 overflow-hidden rounded-full bg-ink-wash",
        className,
      )}
      {...rest}
    >
      <div
        className="absolute inset-y-0 left-0 w-full origin-left bg-brand transition-transform duration-500 ease-out"
        style={{ transform: `scaleX(${fill})` }}
      />
    </div>
  );
}

export const Stepper = Object.assign(StepperRoot, {
  Step,
  Indicator,
  Content,
  Title,
  Description,
  Icon,
  Separator,
});
