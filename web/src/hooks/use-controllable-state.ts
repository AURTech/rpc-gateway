"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Minimal controlled/uncontrolled state hook — local stand-in for
 * `@radix-ui/react-use-controllable-state` (which isn't a direct dependency
 * here). Lets a component accept either `value` (controlled) or fall back to
 * `defaultValue` (uncontrolled), always firing `onChange` on updates.
 *
 * Naming follows components.build: expose `value` / `defaultValue` /
 * `onValueChange` on the consuming component.
 */
export function useControllableState<T>(params: {
  value: T | undefined;
  defaultValue: T;
  onChange?: (value: T) => void;
}): [T, (next: T) => void] {
  const { value, defaultValue, onChange } = params;
  const isControlled = value !== undefined;
  const [uncontrolled, setUncontrolled] = useState(defaultValue);

  // Keep the latest onChange without forcing setValue to change identity.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const stateValue = isControlled ? value : uncontrolled;

  const setValue = useCallback(
    (next: T) => {
      if (!isControlled) setUncontrolled(next);
      onChangeRef.current?.(next);
    },
    [isControlled],
  );

  return [stateValue, setValue];
}
