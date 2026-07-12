import { create } from 'zustand'

export interface AuthUser {
  id: string
  email: string
  name: string
  avatar_url?: string
  authProvider?: string
}

interface AuthState {
  user: AuthUser | null
  loading: boolean
  setUser: (user: AuthUser | null) => void
  setLoading: (loading: boolean) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  setUser: (user) => set({ user, loading: false }),
  setLoading: (loading) => set({ loading }),
  clear: () => set({ user: null, loading: false }),
}))
