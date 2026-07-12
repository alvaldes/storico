import * as TooltipPrimitive from "@base-ui/react/tooltip"
import { cn } from "@/lib/utils"

function TooltipProvider({
  delay,
  closeDelay,
  timeout,
  children,
  ...props
}: TooltipPrimitive.Provider.Props) {
  return (
    <TooltipPrimitive.Provider
      delay={delay}
      closeDelay={closeDelay}
      timeout={timeout}
      {...props}
    >
      {children}
    </TooltipPrimitive.Provider>
  )
}

function Tooltip({
  defaultOpen,
  open,
  onOpenChange,
  disabled,
  disableHoverablePopup,
  trackCursorAxis,
  ...props
}: TooltipPrimitive.Root.Props) {
  return (
    <TooltipPrimitive.Root
      defaultOpen={defaultOpen}
      open={open}
      onOpenChange={onOpenChange}
      disabled={disabled}
      disableHoverablePopup={disableHoverablePopup}
      trackCursorAxis={trackCursorAxis}
      {...props}
    />
  )
}

function TooltipTrigger({
  className,
  ...props
}: TooltipPrimitive.Trigger.Props) {
  return (
    <TooltipPrimitive.Trigger
      className={cn("inline-flex", className)}
      {...props}
    />
  )
}

function TooltipContent({
  className,
  sideOffset = 4,
  children,
  ...props
}: TooltipPrimitive.Popup.Props & { sideOffset?: number }) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Positioner sideOffset={sideOffset}>
        <TooltipPrimitive.Popup
          className={cn(
            "z-50 overflow-hidden rounded-md border bg-popover px-3 py-1.5 text-xs text-popover-foreground shadow-md",
            "data-[open]:animate-in data-[open]:fade-in-0 data-[open]:zoom-in-95",
            "data-[closed]:animate-out data-[closed]:fade-out-0 data-[closed]:zoom-out-95",
            "data-[side=top]:slide-in-from-bottom-1",
            "data-[side=bottom]:slide-in-from-top-1",
            "data-[side=left]:slide-in-from-right-1",
            "data-[side=right]:slide-in-from-left-1",
            className,
          )}
          {...props}
        >
          {children}
          <TooltipPrimitive.Arrow className="fill-border" />
        </TooltipPrimitive.Popup>
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  )
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
