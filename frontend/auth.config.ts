import GitHub from '@auth/core/providers/github'
import Google from '@auth/core/providers/google'
import { defineConfig } from 'auth-astro'
import { config } from './src/lib/config'

// For ngrok or other reverse proxies, set AUTH_URL to the public HTTPS URL.
// Auth.js uses this as the base for all OAuth callback URLs.
// Falls back to localhost for direct development.
const AUTH_URL = process.env.AUTH_URL || 'http://localhost:4321'

export default defineConfig({
  // Explicit base URL — overrides auto-detection so ngrok HTTPS callbacks
  // work correctly (otherwise Auth.js uses http:// from the local proxy).
  base: AUTH_URL,
  providers: [
    GitHub({
      clientId: config.github.clientId || undefined,
      clientSecret: config.github.clientSecret || undefined,
    }),
    Google({
      clientId: config.google.clientId || undefined,
      clientSecret: config.google.clientSecret || undefined,
    }),
  ],
  secret: config.authSecret,
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.auth_provider = account.provider
        token.auth_provider_id = account.providerAccountId

        // Sync user to Storico DB on first login — stores the DB-generated
        // user ID in the JWT so the proxy can forward it as X-Storico-User-Id.
        try {
          const res = await fetch(`${config.apiUrl}/api/v1/auth/sync`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Storico-Internal-Token': config.internalToken,
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
