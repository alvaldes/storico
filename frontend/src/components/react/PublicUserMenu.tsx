'use client';

import { LayoutDashboard, LogOut, FolderKanban, User as UserIcon } from 'lucide-react';
import { signOut } from 'auth-astro/client';

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTranslations, type Locale } from '@/i18n/utils';
import { getInitials } from '@/lib/initials';

export interface PublicNavUser {
  name: string;
  email: string;
  avatarUrl?: string | null;
}

export function PublicUserMenu({ locale, user }: { locale: Locale; user: PublicNavUser }) {
  const t = useTranslations(locale);
  const L = (path: string) => `/${locale}${path}`;
  const initials = getInitials(user.name);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full"
            aria-label={t.nav.open_user_menu}
          />
        }
      >
        <Avatar>
          <AvatarImage src={user.avatarUrl ?? ''} alt={user.name} />
          <AvatarFallback>{initials}</AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-64">
        {/* Anchor width comes from a 32px icon button; min-w-64 keeps the header readable. */}
        <DropdownMenuGroup>
          <DropdownMenuLabel className="p-0 font-normal">
            <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
              <Avatar>
                <AvatarImage src={user.avatarUrl ?? ''} alt={user.name} />
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
              <div className="grid min-w-0 flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">{user.name}</span>
                <span className="truncate text-xs text-muted-foreground">{user.email}</span>
              </div>
            </div>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem render={<a href={L('/dashboard')} />}>
            <LayoutDashboard className="size-4" />
            {t.nav.dashboard}
          </DropdownMenuItem>
          <DropdownMenuItem render={<a href={L('/account')} />}>
            <UserIcon className="size-4" />
            {t.nav.account}
          </DropdownMenuItem>
          <DropdownMenuItem render={<a href={L('/projects')} />}>
            <FolderKanban className="size-4" />
            {t.nav.projects}
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem variant="destructive" onClick={() => signOut({ callbackUrl: `/${locale}/login` })}>
            <LogOut className="size-4" />
            {t.nav.logout}
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
