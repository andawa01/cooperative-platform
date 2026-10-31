/**
 * Application shell: top bar + responsive navigation.
 *
 * Navigation is role-aware:
 * - All users see: Dashboard, Farmers, Deliveries, Payments.
 * - Admins additionally see: Notifications, Produce & Rates.
 *
 * Mobile: bottom tab bar with icons.
 * Desktop: side navigation.
 *
 * The clerk-in-the-field usage is the priority, so mobile layouts are
 * built first and enhanced upward.
 */
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Banknote,
  Bell,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Package,
  Sprout,
  Users,
} from 'lucide-react'

import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  adminOnly?: boolean
  primary?: boolean // shown in mobile bottom nav
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, primary: true },
  { to: '/farmers', label: 'Farmers', icon: Users, primary: true },
  { to: '/deliveries', label: 'Deliveries', icon: Package, primary: true },
  { to: '/payments', label: 'Payments', icon: Banknote, primary: true },
  { to: '/notifications', label: 'Notifications', icon: Bell, adminOnly: true },
  { to: '/produce', label: 'Produce & Rates', icon: Sprout, adminOnly: true },
  { to: '/account', label: 'Account', icon: KeyRound },
]

export function AppShell() {
  const { user, logout, isAdmin } = useAuth()
  const navigate = useNavigate()

  const items = NAV.filter((i) => !i.adminOnly || isAdmin)
  const primaryItems = items.filter((i) => i.primary)

  const handleLogout = async () => {
    // Revokes the token server-side, then clears local state. Always lands on
    // the login screen, even if the revoke call could not reach the server.
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-gray-200 bg-white">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold text-primary-700">
              ShambaTrack
            </span>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <div className="text-sm font-medium text-gray-900">
                {user?.full_name}
              </div>
              <div className="text-xs capitalize text-gray-500">
                {user?.role}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="rounded-md p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900"
              aria-label="Sign out"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl">
        {/* Desktop side nav */}
        <aside className="hidden w-56 shrink-0 border-r border-gray-200 bg-white md:block">
          <nav className="sticky top-14 flex flex-col gap-1 p-3">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition',
                    isActive
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-gray-700 hover:bg-gray-100',
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <main className="min-w-0 flex-1 pb-20 md:pb-0">
          <Outlet />
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="fixed bottom-0 left-0 right-0 z-20 border-t border-gray-200 bg-white md:hidden">
        <div className="flex justify-around">
          {primaryItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex flex-1 flex-col items-center gap-1 py-2 text-xs font-medium',
                  isActive ? 'text-primary-700' : 'text-gray-500',
                )
              }
            >
              <item.icon className="h-5 w-5" />
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}