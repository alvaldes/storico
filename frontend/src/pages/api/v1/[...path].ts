import type { APIRoute } from 'astro'
import { getSession } from 'auth-astro/server'

const API_BASE = import.meta.env.API_URL || 'http://127.0.0.1:8000'
const INTERNAL_TOKEN =
  import.meta.env.STORICO_AUTH_INTERNAL_TOKEN || 'dev-insecure-token-change-in-production'

export const ALL: APIRoute = async ({ request, params }) => {
  const session = await getSession(request)

  if (!session?.user?.id) {
    return new Response(
      JSON.stringify({ detail: 'Unauthorized', type: 'auth_required' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )
  }

  const path = params.path || ''
  const url = `${API_BASE}/api/v1/${path}`

  const headers = new Headers(request.headers)
  headers.set('X-Storico-User-Id', session.user.id as string)
  headers.set('X-Storico-Internal-Token', INTERNAL_TOKEN)

  // Remove host header to avoid conflicts
  headers.delete('host')

  try {
    const backendResponse = await fetch(url, {
      method: request.method,
      headers,
      body: request.body,
      // @ts-ignore — duplex is required for streaming body
      duplex: 'half',
    })

    const responseBody = await backendResponse.text()

    return new Response(responseBody, {
      status: backendResponse.status,
      headers: {
        'Content-Type':
          backendResponse.headers.get('Content-Type') || 'application/json',
      },
    })
  } catch (error) {
    return new Response(
      JSON.stringify({ detail: 'Backend unavailable', type: 'proxy_error' }),
      { status: 502, headers: { 'Content-Type': 'application/json' } },
    )
  }
}
