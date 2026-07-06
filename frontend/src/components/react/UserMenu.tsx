import { useEffect } from 'react'
import { signOut } from 'auth-astro/client'
import { LogOut } from 'lucide-react'
import { useAuthStore, type AuthUser } from '@/stores/authStore'

interface UserMenuProps {
  userJson: string
}

export function UserMenu({ userJson }: UserMenuProps) {
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
    <div className="flex items-center gap-2">
      <span className="text-sm text-(--color-text-secondary) hidden sm:inline">
        {user.name}
      </span>
      <button
        onClick={() => signOut()}
        className="rounded-md p-1.5 text-(--color-text-secondary) hover:bg-(--color-surface-secondary) transition-colors"
        title="Sign out"
      >
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  )
}
