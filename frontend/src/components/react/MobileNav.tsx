"use client";

import { useEffect, useState } from "react";
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Menu, X } from "lucide-react";

export interface MobileNavLink {
  href: string;
  label: string;
  category?: string;
}

interface MobileNavProps {
  links: MobileNavLink[];
  brandName: string;
  locale: string;
  langToggleHref: string;
  cta: { href: string; label: string };
  activePath?: string;
}

export function MobileNav({
  links,
  brandName,
  locale,
  langToggleHref,
  cta,
  activePath: _activePath,
}: MobileNavProps) {
  const [open, setOpen] = useState(false);

  // Compute active path from window.location (handles View Transitions client-side nav)
  const [currentPath, setCurrentPath] = useState(() =>
    typeof window !== "undefined"
      ? window.location.pathname
      : (_activePath ?? ""),
  );

  useEffect(() => {
    function onSwap() {
      setCurrentPath(window.location.pathname);
    }
    document.addEventListener("astro:after-swap", onSwap);
    return () => document.removeEventListener("astro:after-swap", onSwap);
  }, []);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Toggle menu"
          >
            <Menu className="h-5 w-5" />
          </Button>
        }
      />
      <SheetContent
        side="right"
        showCloseButton={false}
        className="rounded-bl-xl rounded-br-xl data-[side=right]:border-0"
        style={{ top: "3.75rem", bottom: "auto", height: "auto" }}
      >
        <SheetHeader className="flex flex-row items-center justify-between">
          <SheetTitle>{brandName}</SheetTitle>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted transition-colors"
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
          </button>
        </SheetHeader>

        <nav className="flex flex-col px-4">
          {(() => {
            const grouped: Record<string, MobileNavLink[]> = {};
            for (const link of links) {
              const cat = link.category || "";
              if (!grouped[cat]) grouped[cat] = [];
              grouped[cat].push(link);
            }
            return Object.entries(grouped).map(([category, categoryLinks]) => (
              <div
                key={category}
                className="flex flex-col gap-0.5 pb-3 last:pb-0"
              >
                {category && (
                  <div>
                    {/* <p className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground"> */}
                    {/*   {category} */}
                    {/* </p> */}
                    <hr className="border-t border-border my-1" />
                  </div>
                )}
                {categoryLinks.map((link) => {
                  const isActive = currentPath === link.href;
                  return (
                    <a
                      key={link.href}
                      href={link.href}
                      onClick={() => setOpen(false)}
                      className={`rounded-lg px-3 py-2.5 text-xs font-normal no-underline transition-colors ${
                        isActive
                          ? "bg-muted text-foreground font-semibold"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      {link.label}
                    </a>
                  );
                })}
              </div>
            ));
          })()}
        </nav>

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
  );
}
