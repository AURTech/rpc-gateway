"use client";

import { format } from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type * as React from "react";
import {
  type DateRange,
  type DayButtonProps,
  DayPicker,
  getDefaultClassNames,
  useDayPicker,
} from "react-day-picker";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Calendar — react-day-picker (v10) wrapped to match the dashboard's design
 * tokens. Selection styling lives on the day button (so range strips stay
 * continuous) and is driven by `data-*` attributes set in {@link CalendarDayButton},
 * keeping every class a named token to satisfy `lint-no-arbitrary-tw`.
 */
function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: React.ComponentProps<typeof DayPicker>) {
  const defaultClassNames = getDefaultClassNames();

  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      // Two-letter weekday headers (Su Mo Tu …) to match the picker reference.
      formatters={{ formatWeekdayName: (date) => format(date, "EEEEEE") }}
      className={cn("p-3", className)}
      classNames={{
        months: cn(
          "relative flex flex-col gap-4 sm:flex-row",
          defaultClassNames.months,
        ),
        month: cn("flex w-full flex-col gap-4", defaultClassNames.month),
        month_caption: cn(
          "flex h-8 items-center justify-center",
          defaultClassNames.month_caption,
        ),
        caption_label: cn(
          "text-sm font-medium text-ink-900",
          defaultClassNames.caption_label,
        ),
        nav: cn(
          "absolute inset-x-0 top-0 flex items-center justify-between",
          defaultClassNames.nav,
        ),
        button_previous: cn(
          buttonVariants({ variant: "ghost", size: "icon-sm" }),
          "text-ink-500",
          defaultClassNames.button_previous,
        ),
        button_next: cn(
          buttonVariants({ variant: "ghost", size: "icon-sm" }),
          "text-ink-500",
          defaultClassNames.button_next,
        ),
        month_grid: cn("w-full border-collapse", defaultClassNames.month_grid),
        weekdays: cn("flex", defaultClassNames.weekdays),
        weekday: cn(
          "flex-1 text-xs font-normal text-ink-400",
          defaultClassNames.weekday,
        ),
        week: cn("mt-1 flex w-full", defaultClassNames.week),
        day: cn(
          "relative flex-1 p-0 text-center text-sm",
          defaultClassNames.day,
        ),
        today: cn(
          "[&>button]:font-semibold [&>button]:text-brand",
          defaultClassNames.today,
        ),
        outside: cn(
          "[&>button]:text-ink-400 [&>button]:opacity-50",
          defaultClassNames.outside,
        ),
        disabled: cn(
          "[&>button]:text-ink-400 [&>button]:opacity-50",
          defaultClassNames.disabled,
        ),
        hidden: cn("invisible", defaultClassNames.hidden),
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation, className: cls }) => {
          const Icon = orientation === "left" ? ChevronLeft : ChevronRight;
          return <Icon className={cn("size-4", cls)} aria-hidden />;
        },
        DayButton: CalendarDayButton,
      }}
      {...props}
    />
  );
}

function CalendarDayButton({
  className,
  day,
  modifiers,
  ...props
}: DayButtonProps) {
  // The calendar always runs in range mode, so `selected` is a DateRange.
  const range = useDayPicker().selected as DateRange | undefined;
  // Only flatten the endpoint corners once the range actually spans more than
  // one day; a lone "from" pick (no "to" yet) or a single-day range stays a
  // fully rounded square.
  const spansDays = Boolean(
    range?.from && range?.to && range.from.getTime() !== range.to.getTime(),
  );
  const isStart = modifiers.range_start && spansDays;
  const isEnd = modifiers.range_end && spansDays;
  const isMiddle = modifiers.range_middle;
  const isSingle = modifiers.selected && !isStart && !isEnd && !isMiddle;

  return (
    <Button
      type="button"
      variant="ghost"
      data-day={day.date.toLocaleDateString()}
      data-selected-single={isSingle}
      data-range-start={isStart}
      data-range-middle={isMiddle}
      data-range-end={isEnd}
      className={cn(
        "flex h-8 w-full rounded-md font-normal text-ink-700",
        // Solid brand for single picks and range endpoints.
        "data-[selected-single=true]:bg-brand data-[selected-single=true]:text-white data-[selected-single=true]:hover:bg-brand-hover",
        "data-[range-start=true]:rounded-r-none data-[range-start=true]:bg-brand data-[range-start=true]:text-white data-[range-start=true]:hover:bg-brand-hover",
        "data-[range-end=true]:rounded-l-none data-[range-end=true]:bg-brand data-[range-end=true]:text-white data-[range-end=true]:hover:bg-brand-hover",
        // Subtle wash for the days between the endpoints.
        "data-[range-middle=true]:rounded-none data-[range-middle=true]:bg-accent data-[range-middle=true]:text-accent-foreground",
        className,
      )}
      {...props}
    />
  );
}

export { Calendar };
