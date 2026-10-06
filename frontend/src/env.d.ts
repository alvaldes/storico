/// <reference types="astro/client" />
import type { Session } from '@auth/core/types';

declare global {
  namespace App {
    interface Locals {
      // Optional because the middleware assigns it only where a guard consumes it — the
      // protected-path branch in `src/middleware.ts` loads the session (and its `auth-astro/server`
      // import) lazily, so `locals.session` is absent on every path that never reads it. The
      // non-optional `Session | null` lied by omission and invited code that trusted a session
      // that is not there.
      session?: Session | null;
    }
  }
}
