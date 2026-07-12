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

  if (request.body) {
    headers.set('Content-Type', 'application/json')
  }

  try {
    const fetchInit: RequestInit & { duplex?: string } = {
      method: request.method,
      headers,
    }

    // Only pass body for non-GET/non-HEAD requests
    if (request.body && request.method !== 'GET' && request.method !== 'HEAD') {
      fetchInit.body = request.body
      // duplex is required by Node.js fetch when body is a ReadableStream
      fetchInit.duplex = 'half'
    }

    const backendResponse = await fetch(url, fetchInit)

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
