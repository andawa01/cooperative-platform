/**
 * Authenticated CSV download.
 *
 * The export endpoints require a bearer token, so a plain `<a href>` cannot
 * reach them — the browser would send no Authorization header and get a 401.
 * This fetches the file, then hands it to a temporary object URL.
 *
 * The filename comes from the server's `Content-Disposition`, which is in the
 * API's CORS `expose_headers` list. If that header is ever missing we fall
 * back to the path, so a download never fails just because of its name.
 */
import { getToken } from './auth'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function downloadCsv(
  path: string,
  params: Record<string, string | number | boolean | undefined> = {},
): Promise<void> {
  const url = new URL(path, BASE_URL)
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '' && value !== false) {
      url.searchParams.set(key, String(value))
    }
  }

  const token = getToken()
  const res = await fetch(url.toString(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })

  if (!res.ok) {
    // Surface the server's message when it sent one; a bare status code
    // leaves the clerk with nothing to quote when reporting a failure.
    let detail = `Export failed (HTTP ${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // Non-JSON error body — keep the status-code message.
    }
    throw new Error(detail)
  }

  const blob = await res.blob()
  const disposition = res.headers.get('content-disposition') ?? ''
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const filename =
    match?.[1] ?? `${path.replace(/^\//, '').replace(/\//g, '-')}.csv`

  const href = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}
