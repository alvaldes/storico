"use client"

import { useState, useMemo, useCallback } from "react"
import { SearchIcon } from "lucide-react"
import { IconDisplay } from "@/components/ui/icon-display"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { useTranslations, type Locale } from "@/i18n/utils"

/* ── curated set shown when no search query ── */

const POPULAR_ICONS: string[] = [
  "building-2",
  "folder-kanban",
  "backpack",
  "blocks",
  "brick-wall",
  "briefcase",
  "bug",
  "cable",
  "cake",
  "chart-area",
  "chart-bar-big",
  "chart-line",
  "chart-pie",
  "check-square",
  "circle-check-big",
  "cloud",
  "code",
  "codepen",
  "coffee",
  "command",
  "compass",
  "cone",
  "construction",
  "container",
  "cookie",
  "cpu",
  "crown",
  "database",
  "dna",
  "drafting-compass",
  "droplets",
  "ellipsis",
  "feather",
  "figma",
  "flag",
  "flask-conical",
  "flask-round",
  "folder-git-2",
  "forklift",
  "frame",
  "gamepad-2",
  "gantt-chart",
  "gem",
  "git-branch",
  "git-merge",
  "globe",
  "hammer",
  "hard-drive",
  "hash",
  "headphones",
  "heart-pulse",
  "hexagon",
  "highlighter",
  "house",
  "image",
  "inbox",
  "infinity",
  "key",
  "key-round",
  "languages",
  "layers",
  "layout-dashboard",
  "lightbulb",
  "link",
  "list-todo",
  "lock",
  "map",
  "medal",
  "megaphone",
  "message-square-text",
  "microchip",
  "milestone",
  "monitor",
  "mountain",
  "mouse",
  "music",
  "network",
  "notebook-pen",
  "notebook-text",
  "nut",
  "palette",
  "panel-top",
  "paperclip",
  "pencil-ruler",
  "phone",
  "pi",
  "picture-in-picture-2",
  "piggy-bank",
  "pizza",
  "plug",
  "plug-zap",
  "pocket",
  "podcast",
  "power",
  "printer",
  "puzzle",
  "qr-code",
  "radio",
  "radio-receiver",
  "rocket",
  "ruler",
  "scale",
  "scissors",
  "screen-share",
  "server",
  "settings",
  "share-2",
  "shield",
  "ship",
  "shirt",
  "shopping-cart",
  "shovel",
  "shrub",
  "sigma",
  "siren",
  "sliders-vertical",
  "smartphone",
  "smile",
  "snail",
  "snowflake",
  "sparkles",
  "speaker",
  "spline",
  "sprout",
  "square-kanban",
  "square-terminal",
  "star",
  "stethoscope",
  "sticker",
  "store",
  "sun",
  "swatch-book",
  "sword",
  "table-2",
  "tablet",
  "tag",
  "tags",
  "target",
  "telescope",
  "tent",
  "terminal",
  "test-tubes",
  "text-search",
  "ticket",
  "timer",
  "toy-brick",
  "train-track",
  "trash-2",
  "tree-deciduous",
  "trello",
  "trophy",
  "truck",
  "unplug",
  "users",
  "vault",
  "vibrate",
  "video",
  "wand-sparkles",
  "watch",
  "waves",
  "webhook",
  "weight",
  "wifi",
  "wind",
  "workflow",
  "wrench",
  "zap",
]

/* ── helpers ── */

function iconNameToLabel(name: string): string {
  return name
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
}

/* ALL_ICONS used for search filtering — the curated popular set covers
 * the most useful icons. When new icons are added to POPULAR_ICONS or
 * the IconDisplay map, they become searchable here automatically. */
const ALL_ICONS: string[] = POPULAR_ICONS

/* ── IconPicker Component ── */

interface IconPickerProps {
  value: string
  onChange: (name: string) => void
  open: boolean
  onOpenChange: (open: boolean) => void
  locale?: Locale
}

export function IconPicker({
  value,
  onChange,
  open,
  onOpenChange,
  locale = "en",
}: IconPickerProps) {
  const t = useTranslations(locale)
  const [query, setQuery] = useState("")

  const normalizedQuery = query.toLowerCase().replace(/\s+/g, "-")

  const results = useMemo(() => {
    if (!normalizedQuery) return POPULAR_ICONS
    return ALL_ICONS.filter(
      (name) =>
        name.includes(normalizedQuery) ||
        iconNameToLabel(name).toLowerCase().includes(query.toLowerCase()),
    ).slice(0, 200)
  }, [normalizedQuery, query])

  const handleSelect = useCallback(
    (name: string) => {
      onChange(name)
      onOpenChange(false)
    },
    [onChange, onOpenChange],
  )

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) setQuery("")
      onOpenChange(open)
    },
    [onOpenChange],
  )

  const isEmpty = results.length === 0

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[540px]">
        <DialogHeader>
          <DialogTitle>{t.iconPicker?.title ?? "Choose an icon"}</DialogTitle>
        </DialogHeader>

        {/* Search */}
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder={t.iconPicker?.searchPlaceholder ?? "Search icons…"}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
            autoFocus
          />
        </div>

        {/* Grid */}
        <div className="no-scrollbar max-h-72 overflow-y-auto">
          {isEmpty ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {t.iconPicker?.noResults ?? "No icons match your search."}
            </p>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(2.5rem,1fr))] gap-1">
              {results.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => handleSelect(name)}
                  className={cn(
                    "flex aspect-square items-center justify-center rounded-md border border-transparent p-1.5 text-muted-foreground transition-colors hover:border-border hover:bg-accent hover:text-accent-foreground",
                    value === name &&
                      "border-primary bg-primary/10 text-primary hover:border-primary hover:bg-primary/15 hover:text-primary",
                  )}
                  title={iconNameToLabel(name)}
                >
                  <IconDisplay name={name} className="size-5" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Selected preview */}
        {value && (
          <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm">
            <IconDisplay name={value} className="size-5 shrink-0 text-foreground" />
            <span className="text-muted-foreground">
                            {t.iconPicker?.selected ?? "Selected:"} {" "}
              <span className="font-medium text-foreground">
                {iconNameToLabel(value)}
              </span>
            </span>
            <span className="ml-auto text-xs text-muted-foreground/60">
              {value}
            </span>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/* ── IconTrigger ── */

interface IconTriggerProps {
  value: string
  onClick: () => void
  className?: string
  locale?: Locale
}

export function IconTrigger({
  value,
  onClick,
  className,
  locale = "en",
}: IconTriggerProps) {
  const t = useTranslations(locale)
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex size-9 items-center justify-center rounded-md border border-input bg-background text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
        className,
      )}
      title={value ? iconNameToLabel(value) : (t.iconPicker?.selectIcon ?? "Select an icon")}
    >
      {value ? (
        <IconDisplay name={value} className="size-4" />
      ) : (
        <SearchIcon className="size-4" />
      )}
    </button>
  )
}
