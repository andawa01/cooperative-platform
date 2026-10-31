/**
 * Application shell: sidebar navigation, sticky top bar, mobile tab bar.
 *
 * Navigation is role-aware:
 * - All users see: Dashboard, Farmers, Deliveries, Payments.
 * - Admins additionally see: Notifications, Produce & Rates.
 *
 * The clerk-in-the-field usage is the priority, so the mobile layout is built
 * first and enhanced upward: big touch targets, a bottom tab bar, and no
 * gesture-only affordances.
 */
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Banknote,
  Bell,
  ChevronsUpDown,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Moon,
  Package,
  Sprout,
  Sun,
  Users,
} from 'lucide-react'

import { useAuth } from '@/hooks/useAuth'
import { useTheme } from '@/hooks/useTheme'
import { cn, initials } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  adminOnly?: boolean
  primary?: boolean // shown in mobile bottom nav
}

interface NavGroup {
  title: string
  items: NavItem[]
}

const NAV: NavGroup[] = [
  {
    title: 'Operations',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, primary: true },
      { to: '/farmers', label: 'Farmers', icon: Users, primary: true },
      { to: '/deliveries', label: 'Deliveries', icon: Package, primary: true },
      { to: '/payments', label: 'Payments', icon: Banknote, primary: true },
    ],
  },
  {
    title: 'Administration',
    items: [
      { to: '/produce', label: 'Produce & Rates', icon: Sprout, adminOnly: true },
      { to: '/notifications', label: 'Notifications', icon: Bell, adminOnly: true },
      { to: '/account', label: 'Account', icon: KeyRound },
    ],
  },
]

export function AppShell() {
  const { user, logout, isAdmin } = useAuth()
  const { isDark, toggle } = useTheme()
  const navigate = useNavigate()

  const groups = NAV.map((group) => ({
    ...group,
    items: group.items.filter((i) => !i.adminOnly || isAdmin),
  })).filter((group) => group.items.length > 0)

  const primaryItems = groups.flatMap((g) => g.items).filter((i) => i.primary)

  const handleLogout = async () => {
    // Revokes the token server-side, then clears local state. Always lands on
    // the login screen, even if the revoke call could not reach the server.
    await logout()
    navigate('/login', { replace: true })
  }

  const themeLabel = isDark ? 'Switch to light mode' : 'Switch to dark mode'

  return (
    <div className="min-h-screen bg-canvas">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-border/70 bg-sidebar lg:flex">
        <div className="flex h-16 items-center gap-2.5 px-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-white shadow-xs">
            <Sprout className="h-4.5 w-4.5" />
          </span>
          <div className="leading-none">
            <div className="text-[15px] font-semibold tracking-tight text-foreground">
              ShambaTrack
            </div>
            <div className="mt-1 text-[11px] text-muted-foreground">
              Cooperative ledger
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
          {groups.map((group) => (
            <div key={group.title}>
              <div className="px-2.5 pb-1.5 text-[10px] font-semibold tracking-wider text-stone-400 uppercase">
                {group.title}
              </div>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    className={({ isActive }) =>
                      cn(
                        'group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-primary-soft text-primary-ink'
                          : 'text-stone-600 hover:bg-stone-100/80 hover:text-stone-900',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <item.icon
                          className={cn(
                            'h-4 w-4 shrink-0 transition-colors',
                            isActive
                              ? 'text-primary-ink'
                              : 'text-stone-400 group-hover:text-stone-600',
                          )}
                        />
                        <span className="truncate">{item.label}</span>
                        {isActive && (
                          <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary-ink" />
                        )}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-border/70 p-3">
          <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-semibold text-background">
              {user
                ? initials(
                    user.full_name.split(' ')[0] ?? '?',
                    user.full_name.split(' ')[1] ?? '',
                  )
                : '?'}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-foreground">
                {user?.full_name}
              </div>
              <div className="truncate text-[11px] text-muted-foreground capitalize">
                {user?.role}
              </div>
            </div>
            <button
              onClick={handleLogout}
              aria-label="Sign out"
              title="Sign out"
              className="rounded-md p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-700"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="lg:pl-64">
        {/* Top bar */}
        <header className="sticky top-0 z-20 border-b border-border/70 bg-card/80 backdrop-blur-md">
          <div className="flex h-14 items-center justify-between gap-3 px-4 lg:h-16 lg:px-8">
            <div className="flex items-center gap-2 lg:hidden">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary-600 text-white">
                <Sprout className="h-4 w-4" />
              </span>
              <span className="text-sm font-semibold tracking-tight text-foreground">
                ShambaTrack
              </span>
            </div>

            <div className="hidden items-center gap-2 text-[13px] text-muted-foreground lg:flex">
              <ChevronsUpDown className="h-3.5 w-3.5" />
              <span className="capitalize">{user?.role}</span>
              <span className="text-stone-400">/</span>
              <span className="truncate text-foreground">{user?.full_name}</span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={toggle}
                aria-label={themeLabel}
                title={themeLabel}
                aria-pressed={isDark}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-stone-600 shadow-xs transition-colors hover:bg-stone-100 hover:text-foreground focus-visible:ring-2 focus-visible:ring-primary-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none"
              >
                {isDark ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Moon className="h-4 w-4" />
                )}
              </button>

              <button
                onClick={() => navigate('/account')}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-foreground text-[11px] font-semibold text-background transition-opacity hover:opacity-85 lg:hidden"
                aria-label="Account settings"
              >
                {user
                  ? initials(
                      user.full_name.split(' ')[0] ?? '?',
                      user.full_name.split(' ')[1] ?? '',
                    )
                  : '?'}
              </button>
              <button
                onClick={handleLogout}
                className="hidden items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[13px] font-medium text-stone-600 shadow-xs transition-colors hover:bg-stone-50 hover:text-stone-900 lg:inline-flex"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </button>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-4 pt-6 pb-24 lg:px-8 lg:pt-8 lg:pb-12">
          <Outlet />
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-border/70 bg-card/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden">
        <div className="mx-auto flex max-w-lg items-stretch justify-around">
          {primaryItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                cn(
                  'relative flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-medium transition-colors',
                  isActive ? 'text-primary-ink' : 'text-stone-500',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      'flex h-8 w-12 items-center justify-center rounded-full transition-colors',
                      isActive && 'bg-primary-soft',
                    )}
                  >
                    <item.icon className="h-5 w-5" />
                  </span>
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
