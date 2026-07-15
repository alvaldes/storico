"use client";

import * as React from "react";
import { Radio as RadioPrimitive } from "@base-ui/react/radio";
import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group";
import { cn } from "@/lib/utils";

export interface SegmentedOption {
  value: string;
  label: React.ReactNode;
}

interface SegmentedControlProps {
  value: string;
  onValueChange: (value: string) => void;
  options: SegmentedOption[];
  className?: string;
}

/**
 * SegmentedControl — single-select button group.
 *
 * Wraps @base-ui/react RadioGroup in a horizontal segmented button layout.
 * Unlike ToggleGroup, this enforces exactly-one-selected at all times.
 */
export function SegmentedControl({
  value,
  onValueChange,
  options,
  className,
}: SegmentedControlProps) {
  return (
    <RadioGroupPrimitive
      value={value}
      onValueChange={onValueChange}
      className={cn(
        "inline-flex items-center rounded-lg border border-(--color-border) overflow-hidden",
        "divide-x divide-(--color-border) *:min-w-0",
        className,
      )}
    >
      {options.map((opt) => (
        <RadioPrimitive.Root
          key={opt.value}
          value={opt.value}
          className={cn(
            "relative flex-1 px-3.5 py-2 text-sm font-medium transition-all cursor-pointer select-none text-center",
            "hover:bg-(--color-surface-secondary)",
            "data-[checked]:bg-(--color-primary-100) data-[checked]:text-(--color-primary-700)",
            "dark:data-[checked]:bg-(--color-primary-900) dark:data-[checked]:text-(--color-primary-300)",
            "focus-visible:outline-none focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-(--color-primary-500) focus-visible:ring-inset",
            "first:rounded-l-lg last:rounded-r-lg",
          )}
        >
          <span className="inline-flex items-center gap-1.5 justify-center">
            {opt.label}
          </span>
        </RadioPrimitive.Root>
      ))}
    </RadioGroupPrimitive>
  );
}
