'use client';

import * as React from 'react';
import type { ReactNode } from 'react';
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import { AppSidebar } from '@/components/app-sidebar';
import { DashboardHeader } from '@/components/react/DashboardHeader';
import { Toaster } from '@/components/ui/sonner';
import { type Locale } from '@/i18n/utils';
import { useAuthStore, type AuthUser } from '@/stores/authStore';
import { fetchFullUserProfile } from '@/lib/user-api';
import { OnboardingModal } from '@/components/react/OnboardingModal';
import { useThemeHydration } from '@/stores/uiStore';

interface DashboardShellProps {
  locale: Locale;
  currentPath: string;
  userJson: string;
  sidebarDefaultOpen?: boolean;
  children: ReactNode;
}

/**
 * Full dashboard layout with shadcn SidebarProvider.
 *
 * Provides the sidebar context for SidebarTrigger, responsive
 * collapse behavior, and mobile sheet navigation.
 */
export function DashboardShell({
  locale,
  currentPath,
  userJson,
  sidebarDefaultOpen = true,
  children,
}: DashboardShellProps) {
  // Populate auth store from serialised session (used by SettingsPage, etc.)
  const setUser = useAuthStore((s) => s.setUser);
  const setIsFirstLogin = useAuthStore((s) => s.setIsFirstLogin);
  React.useEffect(() => {
    if (userJson) {
      try {
        const parsed: Record<string, unknown> = JSON.parse(userJson);
        const baseUser: AuthUser = {
          id: (parsed.id as string) || '',
          email: (parsed.email as string) || '',
          name: (parsed.name as string) || '',
          avatar_url: (parsed.avatar_url as string) || (parsed.image as string) || undefined,
        };
        setUser(baseUser);
        fetchFullUserProfile()
          .then((profile) => {
            setUser({
              id: profile.user.id,
              email: profile.user.email,
              name: profile.user.name,
              avatar_url: profile.user.avatarUrl,
              authProvider: profile.user.authProvider,
            });
            setIsFirstLogin(profile.user.isFirstLogin);
          })
          .catch(() => {});
      } catch {
        setUser(null);
      }
    } else {
      setUser(null);
    }
  }, [userJson, setUser, setIsFirstLogin]);

  const isFirstLogin = useAuthStore((s) => s.isFirstLogin);

  // One-time post-hydration theme sync for every authenticated page.
  useThemeHydration();

  return (
    <SidebarProvider defaultOpen={sidebarDefaultOpen} className="max-h-svh">
      {isFirstLogin && <OnboardingModal locale={locale} />}
      <AppSidebar locale={locale} currentPath={currentPath} />
      <SidebarInset className="max-h-dvh min-w-0">
        <DashboardHeader locale={locale} currentPath={currentPath} />

        <main className="flex-1 flex flex-col min-w-0 p-4 lg:p-6">
          <div className="relative flex-1 min-h-0 overflow-hidden p-px">{children}</div>
        </main>
      </SidebarInset>
      <Toaster />
    </SidebarProvider>
  );
}
