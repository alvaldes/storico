import type { APIRoute } from 'astro'
import { getSession } from 'auth-astro/server'
import { SignJWT } from 'jose'
import { config } from '@/lib/config'

/** Headers que NO se reenvían del backend al cliente (hop-by-hop + seguridad). */
const HOP_BY_HOP = new Set([
  'transfer-encoding',
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'upgrade',
  'set-cookie',        // auth lo maneja Auth.js, no el backend
  'set-cookie2',       // obsoleto
  'content-encoding',  // Node.fetch ya descomprime
  'content-length',    // lo recalcula el Response constructor
])

/** Tiempo máximo de espera para el backend (en ms).
 *
 * Debe coincidir con el timeout del LLM en ``LLMConfig`` (120s)
 * para evitar 504 del proxy cuando el modelo tarda en responder.
 */
const BACKEND_TIMEOUT = 120_000

/** Limpia un path de segmentos peligrosos (path traversal). */
function sanitizePath(raw: string): string {
  return raw
    .split('/')
    .filter((seg) => seg !== '..' && seg !== '.')
    .join('/')
}

/** Arma la URL del backend normalizando el path. */
function buildBackendUrl(apiUrl: string, rawPath: string): URL {
  const clean = sanitizePath(rawPath)
  // Evitar doble slash al unir
  const joined = clean ? `/api/v1/${clean}` : '/api/v1/'
  return new URL(joined, apiUrl)
}

/** Convierte Headers del backend a un Record plano (excluyendo hop-by-hop). */
function forwardableHeaders(backendHeaders: Headers): Record<string, string> {
  const result: Record<string, string> = {}
  backendHeaders.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      result[key] = value
    }
  })
  return result
}

export const ALL: APIRoute = async ({ request, params }) => {
  const session = await getSession(request)

  if (!session?.user?.id) {
    return new Response(
      JSON.stringify({ detail: 'Unauthorized', type: 'auth_required' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )
  }

  if (!config.apiUrl) {
    return new Response(
      JSON.stringify({ detail: 'Backend URL not configured', type: 'config_error' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } },
    )
  }

  // Build clean headers — do NOT copy from request (avoids ngrok headers,
  // Host conflicts, and other proxy artifacts).
  const headers = new Headers()

  // Create a compact JWT from the Auth.js session, signed with AUTH_SECRET.
  // The backend verifies this JWT to authenticate the user.
  const jwt = await new SignJWT({ sub: session.user.id })
    .setProtectedHeader({ alg: 'HS256' })
    .sign(new TextEncoder().encode(config.authSecret))
  headers.set('Authorization', `Bearer ${jwt}`)

  // AbortController para tener timeout controlado
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), BACKEND_TIMEOUT)

  try {
    // --- Leer body del request ---
    // Leer ANTES de hacer fetch para evitar problemas con ReadableStream
    // en Node.js fetch (evita duplex:'half').
    let rawBody: string | undefined
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      const text = await request.text()
      if (text) {
        rawBody = text
        headers.set('Content-Type', 'application/json')
      }
    }

    // --- Resolver URL del backend ---
    let backendUrl: URL
    try {
      backendUrl = buildBackendUrl(config.apiUrl, params.path ?? '')

      // Reenviar query params de la request original al backend.
      // params.path (del catch-all [...path]) NO incluye query string.
      const originalUrl = new URL(request.url)
      originalUrl.searchParams.forEach((value, key) => {
        backendUrl.searchParams.append(key, value)
      })
    } catch {
      return new Response(
        JSON.stringify({ detail: 'Invalid backend URL', type: 'config_error' }),
        { status: 500, headers: { 'Content-Type': 'application/json' } },
      )
    }

    // --- Enviar al backend ---
    const backendResponse = await fetch(backendUrl, {
      method: request.method,
      headers,
      body: rawBody,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    // Loggear errores del backend para debugging
    if (!backendResponse.ok) {
      console.warn(
        `[api/v1] backend ${backendResponse.status} ${backendResponse.statusText} — ${request.method} ${backendUrl.pathname}`,
      )
    }

    // --- Procesar respuesta ---
    // 204/304 no tienen body — evitar errores al leer .text()
    if (backendResponse.status === 204 || backendResponse.status === 304) {
      return new Response(null, { status: backendResponse.status })
    }

    const responseBody = await backendResponse.text()

    return new Response(responseBody, {
      status: backendResponse.status,
      headers: forwardableHeaders(backendResponse.headers),
    })
  } catch (error) {
    clearTimeout(timeoutId)

    if (error instanceof DOMException && error.name === 'AbortError') {
      console.error('[api/v1] backend timeout:', request.method, config.apiUrl)
      return new Response(
        JSON.stringify({ detail: 'Backend timeout', type: 'proxy_timeout' }),
        { status: 504, headers: { 'Content-Type': 'application/json' } },
      )
    }

    console.error('[api/v1] proxy error:', error)
    return new Response(
      JSON.stringify({ detail: 'Backend unavailable', type: 'proxy_error' }),
      { status: 502, headers: { 'Content-Type': 'application/json' } },
    )
  }
}
