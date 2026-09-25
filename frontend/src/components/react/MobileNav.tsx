'use client';

import { useEffect, useState } from 'react';
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Menu, X, LogOut, ChevronRight } from 'lucide-react';
import { signOut } from 'auth-astro/client';
import { useTranslations, type Locale } from '@/i18n/utils';
import { getInitials } from '@/lib/initials';
import { type PublicNavUser } from '@/components/react/PublicUserMenu';

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
  /** Serialized session user; null/undefined when signed out. */
  user?: PublicNavUser | null;
}

export function MobileNav({
  links,
  brandName,
  locale,
  langToggleHref,
  cta,
  activePath: _activePath,
  user,
}: MobileNavProps) {
  const t = useTranslations(locale as Locale);
  const [open, setOpen] = useState(false);

  // Compute active path from window.location (handles View Transitions client-side nav)
  const [currentPath, setCurrentPath] = useState(() =>
    typeof window === 'undefined' ? (_activePath ?? '') : window.location.pathname,
  );

  useEffect(() => {
    function onSwap() {
      setCurrentPath(window.location.pathname);
    }
    document.addEventListener('astro:after-swap', onSwap);
    return () => document.removeEventListener('astro:after-swap', onSwap);
  }, []);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label={t.nav?.toggleMenu ?? 'Toggle menu'}
          >
            <Menu className="h-5 w-5" />
          </Button>
        }
      />
      <SheetContent
        side="right"
        showCloseButton={false}
        className="max-h-[calc(100dvh-var(--public-nav-h,4.25rem))] rounded-bl-xl rounded-br-xl data-[side=right]:border-0"
        style={{ top: 'var(--public-nav-h, 4.25rem)', bottom: 'auto', height: 'auto' }}
      >
        <SheetHeader className="flex shrink-0 flex-row items-center justify-between gap-2 border-b border-border px-3 py-2">
          {user ? (
            <>
              <a
                href={`/${locale}/account`}
                aria-label={t.nav.account}
                onClick={() => setOpen(false)}
                className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg p-1.5 no-underline transition-colors hover:bg-muted"
              >
                <Avatar className="size-8">
                  <AvatarImage src={user.avatarUrl ?? ''} alt={user.name} />
                  <AvatarFallback className="text-xs">{getInitials(user.name)}</AvatarFallback>
                </Avatar>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-foreground">{user.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                </div>
                <ChevronRight className="ml-auto size-4 shrink-0 text-muted-foreground" />
              </a>
              {/* Exactly one SheetTitle stays in the DOM so the dialog keeps its
                  accessible name; it is hidden here because the identity row
                  already fills the header. */}
              <SheetTitle className="sr-only">{brandName}</SheetTitle>
            </>
          ) : (
            <SheetTitle>{brandName}</SheetTitle>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted transition-colors"
            aria-label={t.nav?.closeMenu ?? 'Close menu'}
          >
            <X className="h-4 w-4" />
          </button>
        </SheetHeader>

        {/* flex-1 is intentionally absent: in an auto-height flex container it is
            `flex: 1 1 0%`, which sets the item's hypothetical main size to 0 and
            collapses the nav. Shrink-only with min-h-0 shrinks the nav exactly
            when the panel's max-height is reached and leaves it content-sized
            otherwise; the header and footer are pinned with shrink-0. */}
        <nav className="flex min-h-0 flex-col overflow-y-auto px-4">
          {(() => {
            const grouped: Record<string, MobileNavLink[]> = {};
            for (const link of links) {
              const cat = link.category || '';
              if (!grouped[cat]) grouped[cat] = [];
              grouped[cat].push(link);
            }
            const groups = Object.entries(grouped);
            // With three or more groups the first one is the primary destination
            // and renders full width, while the remaining short groups pair up in
            // a two-column grid — that is what lets an iPhone SE fit without
            // scrolling. With two or fewer groups everything shares the grid.
            // Below 360px the grid collapses to one column rather than squeezing
            // the text.
            const leadGroup = groups.length > 2 ? groups[0] : null;
            const gridGroups = groups.length > 2 ? groups.slice(1) : groups;
            const renderGroup = ([category, categoryLinks]: [string, MobileNavLink[]]) => (
              <div key={category} className="flex flex-col gap-0.5 pb-3 last:pb-0">
                {category && (
                  <p className="px-2 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {category}
                  </p>
                )}
                {categoryLinks.map((link) => {
                  const isActive = currentPath === link.href;
                  return (
                    <a
                      key={link.href}
                      href={link.href}
                      onClick={() => setOpen(false)}
                      className={`flex h-11 items-center whitespace-nowrap rounded-lg px-2 text-[13px] no-underline transition-colors ${
                        isActive
                          ? 'bg-muted text-foreground font-semibold'
                          : 'text-foreground hover:bg-muted hover:text-foreground'
                      }`}
                    >
                      {link.label}
                    </a>
                  );
                })}
              </div>
            );
            return (
              <>
                {leadGroup && renderGroup(leadGroup)}
                <div className="grid grid-cols-1 gap-x-2 min-[360px]:grid-cols-2">
                  {gridGroups.map(renderGroup)}
                </div>
              </>
            );
          })()}
        </nav>

        <SheetFooter className="shrink-0 border-t border-border">
          <a
            href={cta.href}
            onClick={() => setOpen(false)}
            className="flex h-11 items-center justify-center rounded-lg bg-primary px-5 text-sm font-semibold text-primary-foreground no-underline transition-all hover:bg-primary/80"
          >
            {cta.label}
          </a>
          {user && (
            <Button
              variant="ghost"
              className="w-full"
              onClick={() => {
                setOpen(false);
                signOut({ callbackUrl: `/${locale}/login` });
              }}
            >
              <LogOut className="size-4" />
              {t.nav.logout}
            </Button>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
