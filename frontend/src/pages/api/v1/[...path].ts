import type { APIRoute } from 'astro'
import { getSession } from 'auth-astro/server'
import { config } from '@/lib/config'

export const ALL: APIRoute = async ({ request, params }) => {
  const session = await getSession(request)

  if (!session?.user?.id) {
    return new Response(
      JSON.stringify({ detail: 'Unauthorized', type: 'auth_required' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )
  }

  const path = params.path || ''
  const url = `${config.apiUrl}/api/v1/${path}`

  // Build clean headers — do NOT copy from request (avoids ngrok headers,
  // Host conflicts, and other proxy artifacts).
  const headers = new Headers()
  headers.set('X-Storico-User-Id', session.user.id as string)
  headers.set('X-Storico-Internal-Token', config.internalToken)

  try {
    // Read body as text FIRST (before any other processing) to avoid issues
    // with ReadableStream + duplex options in Node.js fetch.
    let body: string | undefined
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      const text = await request.text()
      if (text) {
        body = text
        headers.set('Content-Type', 'application/json')
      }
    }

    const backendResponse = await fetch(url, {
      method: request.method,
      headers,
      ...(body ? { body } : {}),
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
    console.error('[api/v1] proxy error:', error)
    return new Response(
      JSON.stringify({ detail: 'Backend unavailable', type: 'proxy_error' }),
      { status: 502, headers: { 'Content-Type': 'application/json' } },
    )
  }
}
