"use client";

import { ChevronDown, ListFilter } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface TableColumnFilterProps {
  label: string;
  active?: boolean;
  align?: "start" | "center" | "end";
  contentClassName?: string;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
}

function TableColumnFilterTrigger({
  label,
  active,
  className,
  ...props
}: {
  label: string;
  active: boolean;
} & ComponentProps<"button">) {
  return (
    <button
      type="button"
      className={cn(
        "-mx-2 inline-flex h-8 min-w-0 max-w-full items-center gap-1.5 rounded-md px-2 font-medium text-ink-500 outline-none transition-colors hover:bg-ink-wash hover:text-ink-900 focus-visible:ring-2 focus-visible:ring-brand/30",
        active && "text-brand",
        className,
      )}
      {...props}
    >
      <span className="truncate">{label}</span>
      {active ? (
        <ListFilter className="size-3.5 shrink-0" aria-hidden />
      ) : (
        <ChevronDown className="size-3.5 shrink-0" aria-hidden />
      )}
    </button>
  );
}

function TableColumnFilter({
  label,
  active = false,
  align = "start",
  contentClassName,
  onOpenChange,
  children,
}: TableColumnFilterProps) {
  return (
    <DropdownMenu onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <TableColumnFilterTrigger label={label} active={active} />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align={align}
        className={cn("min-w-44", contentClassName)}
      >
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function TableColumnFilterPanel({
  label,
  active = false,
  align = "start",
  contentClassName,
  onOpenChange,
  children,
}: TableColumnFilterProps) {
  return (
    <Popover onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <TableColumnFilterTrigger label={label} active={active} />
      </PopoverTrigger>
      <PopoverContent align={align} className={contentClassName}>
        {children}
      </PopoverContent>
    </Popover>
  );
}

export { TableColumnFilter, TableColumnFilterPanel };
