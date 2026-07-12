import { useEffect } from 'react'
import { signOut } from 'auth-astro/client'
import { LogOut } from 'lucide-react'
import { useAuthStore, type AuthUser } from '@/stores/authStore'
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from '@/components/ui/tooltip'
import { useTranslations, type Locale } from '@/i18n/utils'

interface UserMenuProps {
  userJson: string
  locale?: Locale
}

export function UserMenu({ userJson, locale = 'en' }: UserMenuProps) {
  const t = useTranslations(locale)
  const { user, setUser } = useAuthStore()

  useEffect(() => {
    if (userJson) {
      try {
        const parsed: AuthUser = JSON.parse(userJson)
        setUser(parsed)
      } catch {
        setUser(null)
      }
    } else {
      setUser(null)
    }
  }, [userJson, setUser])

  if (!user) return null

  return (
    <TooltipProvider>
      <div className="flex items-center gap-2">
        <span className="text-sm text-(--color-text-secondary) hidden sm:inline">
          {user.name}
        </span>
        <Tooltip>
          <TooltipTrigger
            onClick={() => signOut()}
            className="rounded-md p-1.5 text-(--color-text-secondary) hover:bg-(--color-surface-secondary) transition-colors"
            aria-label={t.nav.logout}
          >
            <LogOut className="h-4 w-4" />
          </TooltipTrigger>
          <TooltipContent>{t.nav.logout}</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  )
}
