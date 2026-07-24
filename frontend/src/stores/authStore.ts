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
  isFirstLogin: boolean
  setUser: (user: AuthUser | null) => void
  setIsFirstLogin: (flag: boolean) => void
  setOnboardingDone: () => void
  setLoading: (loading: boolean) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  isFirstLogin: false,
  setUser: (user) => set({ user, loading: false }),
  setIsFirstLogin: (flag) => set({ isFirstLogin: flag }),
  setOnboardingDone: () => set({ isFirstLogin: false }),
  setLoading: (loading) => set({ loading }),
  clear: () => set({ user: null, loading: false, isFirstLogin: false }),
}))
