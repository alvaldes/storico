"use client"

import { useState } from "react"
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Menu, X } from "lucide-react"

export interface MobileNavLink {
  href: string
  label: string
}

interface MobileNavProps {
  links: MobileNavLink[]
  brandName: string
  locale: string
  langToggleHref: string
  cta: { href: string; label: string }
}

export function MobileNav({ links, brandName, locale, langToggleHref, cta }: MobileNavProps) {
  const [open, setOpen] = useState(false)

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Toggle menu">
            <Menu className="h-5 w-5" />
          </Button>
        }
      />
      <SheetContent side="right" showCloseButton={false}>
        <SheetHeader className="flex flex-row items-center justify-between">
          <SheetTitle>{brandName}</SheetTitle>
          {/* Close via base-ui's internal Close won't work with render prop polymorphism here;
              we add a simple close button in the header. The Sheet also closes on overlay click. */}
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted transition-colors"
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
          </button>
        </SheetHeader>

        <nav className="flex flex-col gap-1 px-4">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="rounded-lg px-3 py-2.5 text-[15px] font-medium text-muted-foreground no-underline transition-colors hover:bg-muted hover:text-foreground"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="px-4 mt-2">
          <a
            href={langToggleHref}
            onClick={() => setOpen(false)}
            className="inline-flex items-center rounded-lg px-3 py-2.5 text-xs font-bold uppercase tracking-wider text-muted-foreground no-underline transition-colors hover:text-foreground"
          >
            {locale === "en" ? "ES" : "EN"}
          </a>
        </div>

        <SheetFooter>
          <a
            href={cta.href}
            onClick={() => setOpen(false)}
            className="flex items-center justify-center rounded-lg bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground no-underline transition-all hover:bg-primary/80"
          >
            {cta.label}
          </a>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
