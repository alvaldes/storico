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
  workspaceName: string
  setUser: (user: AuthUser | null) => void
  setIsFirstLogin: (flag: boolean) => void
  setWorkspaceName: (name: string) => void
  setOnboardingDone: () => void
  setLoading: (loading: boolean) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  isFirstLogin: false,
  workspaceName: '',
  setUser: (user) => set({ user, loading: false }),
  setIsFirstLogin: (flag) => set({ isFirstLogin: flag }),
  setWorkspaceName: (name) => set({ workspaceName: name }),
  setOnboardingDone: () => set({ isFirstLogin: false }),
  setLoading: (loading) => set({ loading }),
  clear: () => set({ user: null, loading: false, isFirstLogin: false, workspaceName: '' }),
}))
