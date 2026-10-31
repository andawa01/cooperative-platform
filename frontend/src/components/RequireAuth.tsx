/**
 * Route wrapper that redirects unauthenticated users to /login.
 *
 * While auth hydration is running (a single tick on first mount), renders
 * nothing so we don't flash the login page.
 */
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return null
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

/**
 * Route wrapper requiring a specific role. Renders a 403-style message if
 * the user lacks the role. Not a security boundary — the backend enforces
 * permissions independently. This is UX.
 */
export function RequireRole({
  roles,
  children,
}: {
  roles: Array<'admin' | 'clerk'>
  children: React.ReactNode
}) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user || !roles.includes(user.role)) {
    return (
      <div className="p-8 max-w-md mx-auto">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6">
          <h2 className="text-lg font-semibold text-amber-900">
            Access denied
          </h2>
          <p className="mt-2 text-sm text-amber-800">
            Your role ({user?.role ?? 'unknown'}) does not permit this page.
          </p>
        </div>
      </div>
    )
  }
  return <>{children}</>
}