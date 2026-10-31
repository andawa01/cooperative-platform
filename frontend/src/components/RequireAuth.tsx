/**
 * Route wrapper that redirects unauthenticated users to /login.
 *
 * While auth hydration is running (a single tick on first mount), renders
 * nothing so we don't flash the login page.
 */
import { Navigate, useLocation } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'

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
      <div className="mx-auto max-w-md py-16">
        <div className="rounded-card border border-warning/25 bg-warning-soft p-6 text-center shadow-card">
          <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-card/70 text-warning-ink">
            <ShieldAlert className="h-5 w-5" />
          </div>
          <h2 className="text-base font-semibold text-warning-ink">
            Access denied
          </h2>
          <p className="mt-1.5 text-sm text-warning-ink/80">
            Your role ({user?.role ?? 'unknown'}) does not permit this page.
          </p>
        </div>
      </div>
    )
  }
  return <>{children}</>
}
