/**
 * Central configuration module for the Storico frontend.
 *
 * All environment variables are validated and exposed through this module.
 * If a required variable is missing, it throws immediately at import time —
 * no silent fallbacks, no surprises.
 */

function required(name: string): string {
  const value = import.meta.env[name]
  if (!value) {
    throw new Error(
      `Missing required environment variable: ${name}\n` +
        `Check frontend/.env or frontend/.env.example for the list of required variables.`,
    )
  }
  return value
}

function optional(name: string, fallback: string): string {
  return import.meta.env[name] || fallback
}

export const config = {
  /** Auth.js base URL — controls OAuth callback URLs. Must be http://localhost:4321 for local dev. */
  authUrl: optional('AUTH_URL', 'http://localhost:4321'),

  /** Backend URL used by Astro API proxy and Auth.js */
  apiUrl: required('API_URL'),

  /** Shared secret between Astro proxy and FastAPI backend */
  internalToken: required('STORICO_AUTH_INTERNAL_TOKEN'),

  /** Auth.js secret for JWT encryption */
  authSecret: required('AUTH_SECRET'),

  /** OAuth providers (optional — at least one needed for login) */
  github: {
    clientId: optional('GITHUB_CLIENT_ID', ''),
    clientSecret: optional('GITHUB_CLIENT_SECRET', ''),
  },

  google: {
    clientId: optional('GOOGLE_CLIENT_ID', ''),
    clientSecret: optional('GOOGLE_CLIENT_SECRET', ''),
  },
} as const

export type Config = typeof config
