/**
 * Auth token storage in localStorage.
 *
 * Documented trade-off (see D-025): localStorage is XSS-vulnerable in
 * principle. We accept this for MVP because we control every script on
 * the origin. If we ever embed third-party content, we move to
 * httpOnly cookies.
 */
import type { User } from '@/types/api'

const TOKEN_KEY = 'shambatrack_token'
const USER_KEY = 'shambatrack_user'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function getStoredUser(): User | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

export function setStoredUser(user: User): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

/**
 * Decode a JWT payload without verification. We only need `exp` for a
 * client-side "is this obviously expired" check; the server is the
 * authority on validity.
 */
export function decodeToken(token: string): { exp?: number; sub?: string } | null {
  try {
    const [, payload] = token.split('.')
    if (!payload) return null
    const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
    return json
  } catch {
    return null
  }
}

export function isTokenExpired(token: string | null): boolean {
  if (!token) return true
  const claims = decodeToken(token)
  if (!claims?.exp) return true
  // 30-second grace window so we don't treat a token expiring "now" as invalid.
  return claims.exp * 1000 < Date.now() - 30_000
}

// ---------------------------------------------------------------------------
// Money helpers
// ---------------------------------------------------------------------------

/**
 * Convert a money string (or number) from the API into a JS number for
 * display arithmetic. Never round-trip through this for storage — send
 * money back to the API as strings.
 */
export function parseMoney(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0
  return typeof value === 'number' ? value : Number(value)
}

export function formatMoney(
  value: string | number | null | undefined,
  currency = 'KES',
): string {
  const n = parseMoney(value)
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n)
}