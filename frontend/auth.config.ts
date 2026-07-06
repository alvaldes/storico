import GitHub from '@auth/core/providers/github'
import Google from '@auth/core/providers/google'
import { defineConfig } from 'auth-astro'

const API_URL = import.meta.env.API_URL || 'http://127.0.0.1:8000'
const INTERNAL_TOKEN =
  import.meta.env.STORICO_AUTH_INTERNAL_TOKEN ||
  'dev-insecure-token-change-in-production'

export default defineConfig({
  providers: [
    GitHub({
      clientId: import.meta.env.GITHUB_CLIENT_ID,
      clientSecret: import.meta.env.GITHUB_CLIENT_SECRET,
    }),
    Google({
      clientId: import.meta.env.GOOGLE_CLIENT_ID,
      clientSecret: import.meta.env.GOOGLE_CLIENT_SECRET,
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.auth_provider = account.provider
        token.auth_provider_id = account.providerAccountId

        // Sync user to Storico DB on first login — stores the DB-generated
        // user ID in the JWT so the proxy can forward it as X-Storico-User-Id.
        try {
          const res = await fetch(`${API_URL}/api/v1/auth/sync`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Storico-Internal-Token': INTERNAL_TOKEN,
            },
            body: JSON.stringify({
              email: token.email ?? '',
              name: token.name ?? '',
              auth_provider: account.provider,
              auth_provider_id: account.providerAccountId,
              avatar_url: token.picture ?? null,
            }),
          })
          if (res.ok) {
            const data = await res.json()
            token.id = data.id
          }
        } catch (error) {
          console.error('Failed to sync user:', error)
        }
      }
      return token
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.auth_provider = token.auth_provider as string
        session.user.auth_provider_id = token.auth_provider_id as string
        session.user.id = token.id as string
      }
      return session
    },
  },
})
