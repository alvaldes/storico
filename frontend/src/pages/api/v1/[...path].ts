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

  const headers = new Headers(request.headers)
  headers.set('X-Storico-User-Id', session.user.id as string)
  headers.set('X-Storico-Internal-Token', config.internalToken)

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
