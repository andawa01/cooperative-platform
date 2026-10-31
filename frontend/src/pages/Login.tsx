import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api'

export default function Login() {
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation() as { state?: { from?: string } }
  // A flag in the URL rather than router state: the account screen may be
  // unmounted by the auth guard in the same tick it redirects here.
  const [params] = useSearchParams()
  const changedPassword = params.get('changed') === '1'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // If already logged in, redirect. This must not run during render:
  // calling navigate() there updates BrowserRouter while Login is still
  // rendering, which React reports as a cross-component setState.
  useEffect(() => {
    if (user) navigate(location.state?.from ?? '/', { replace: true })
  }, [user, location.state, navigate])

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login({ email, password })
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Invalid email or password.')
      } else if (err instanceof ApiError && err.status === 429) {
        // The account is locked after too many failures. Say how long, so
        // the clerk stops retrying instead of assuming the app is broken.
        setError(`Too many failed attempts. ${waitFor(err.retryAfter)}`)
      } else {
        setError('Unable to sign in. Check your connection and try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-semibold text-primary-700">
            ShambaTrack
          </h1>
          <p className="mt-1 text-sm text-gray-600">
            Sign in to your cooperative account
          </p>
        </div>

        {changedPassword && (
          <div className="mb-4 rounded-md bg-primary-50 p-3 text-sm text-primary-800">
            Password changed. Sign in again with your new password.
          </div>
        )}

        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-lg border border-gray-200 bg-white p-6 shadow-sm"
        >
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
          </div>

          {error && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="mt-6 rounded-lg border border-dashed border-gray-300 bg-white/50 p-4 text-xs text-gray-600">
          <p className="font-medium text-gray-700">Demo credentials</p>
          <p className="mt-1">Admin: admin@shambatrack.io / demo-admin-123</p>
          <p>Clerk: clerk1@shambatrack.io / demo-clerk-123</p>
        </div>
      </div>
    </div>
  )
}

/** Turn a Retry-After (seconds) into something a person can act on. */
function waitFor(seconds: number | null): string {
  if (!seconds || seconds <= 0) return 'Try again later.'
  if (seconds < 90) return `Try again in ${Math.ceil(seconds)} seconds.`
  const minutes = Math.ceil(seconds / 60)
  if (minutes < 60) return `Try again in about ${minutes} minutes.`
  return 'Try again later, or ask an admin to reset your password.'
}