/**
 * Type patches for auth-astro v4.2.0.
 *
 * auth-astro ships source .ts files that reference modules not
 * installed as direct or peer dependencies (next-auth) and uses
 * Node.js APIs. These ambient declarations bridge the gap so
 * `npx tsc --noEmit` passes cleanly.
 */

// ── auth:config (Astro virtual module) ──────────────────────────

declare module 'auth:config' {
  import type { AuthConfig } from '@auth/core';

  interface AstroAuthConfig extends AuthConfig {
    prefix?: string;
  }

  const config: AstroAuthConfig;
  export default config;
}

// ── next-auth/react (not installed — peer dep of auth-astro) ────

declare module 'next-auth/react' {
  export type LiteralUnion<T extends U, U = string> = T | (U & { _?: never });

  export interface SignInOptions {
    callbackUrl?: string;
    redirect?: boolean;
  }

  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  export interface SignInAuthorizationParams extends Record<string, string> {}

  export interface SignOutParams {
    callbackUrl?: string;
  }

  export function signIn<P extends string = string>(
    provider?: P,
    options?: SignInOptions & Record<string, unknown>,
    authorizationParams?: string | Record<string, string> | URLSearchParams | string[][],
  ): Promise<void>;

  export function signOut(options?: SignOutParams): Promise<void>;
  export function useSession(): { data: unknown; status: string };
}

// ── set-cookie-parser (missing @types/set-cookie-parser) ────────

declare module 'set-cookie-parser' {
  export function parseString(input: string): Record<string, string>;
}
