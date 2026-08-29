"use client";

import { AnimatePresence, motion } from "motion/react";
import { Popover as PopoverPrimitive } from "radix-ui";
import type * as React from "react";
import { createContext, useContext, useState } from "react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import { menuContentVariants, menuTransition } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Radix Popover wrapped to match the dashboard's motion-driven popper pattern
 * (see {@link DropdownMenuContent}): surface the open state through context so
 * `PopoverContent` can drive `AnimatePresence` and let the scale/fade exit play
 * before unmount. Works for both controlled and uncontrolled callers.
 */

const PopoverContext = createContext<{ open: boolean }>({ open: false });

function Popover({
  open: openProp,
  defaultOpen,
  onOpenChange,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(
    defaultOpen ?? false,
  );
  const isControlled = openProp !== undefined;
  const open = isControlled ? openProp : uncontrolledOpen;
  const handleOpenChange = (next: boolean) => {
    if (!isControlled) setUncontrolledOpen(next);
    onOpenChange?.(next);
  };
  return (
    <PopoverContext.Provider value={{ open }}>
      <PopoverPrimitive.Root
        data-slot="popover"
        open={open}
        onOpenChange={handleOpenChange}
        {...props}
      />
    </PopoverContext.Provider>
  );
}

function PopoverTrigger({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />;
}

function PopoverAnchor({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Anchor>) {
  return <PopoverPrimitive.Anchor data-slot="popover-anchor" {...props} />;
}

function PopoverContent({
  className,
  align = "start",
  sideOffset = 6,
  children,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  const { open } = useContext(PopoverContext);
  const motionPreset = useMotionPreset();
  return (
    <PopoverPrimitive.Portal forceMount>
      <AnimatePresence>
        {open && (
          <PopoverPrimitive.Content
            key="content"
            asChild
            forceMount
            align={align}
            sideOffset={sideOffset}
            {...props}
          >
            <motion.div
              data-slot="popover-content"
              style={{
                transformOrigin:
                  "var(--radix-popover-content-transform-origin)",
              }}
              className={cn(
                "z-50 rounded-xl bg-popover p-1 text-popover-foreground shadow-section outline-none",
                className,
              )}
              variants={menuContentVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={motionPreset.transition(menuTransition)}
            >
              {children}
            </motion.div>
          </PopoverPrimitive.Content>
        )}
      </AnimatePresence>
    </PopoverPrimitive.Portal>
  );
}

export { Popover, PopoverTrigger, PopoverAnchor, PopoverContent };
