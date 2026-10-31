/**
 * Current theme + toggle.
 *
 * `main.tsx` applies the resolved theme before React mounts (and index.html
 * applies it even earlier, before first paint), so this hook only has to keep
 * React state and the DOM in step afterwards.
 */
import { useCallback, useEffect, useState } from 'react'

import {
  DARK_QUERY,
  getStoredTheme,
  resolveTheme,
  setTheme,
  systemTheme,
  type Theme,
} from '@/lib/theme'

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => resolveTheme())

  // Follow the OS only while no explicit choice exists.
  useEffect(() => {
    if (getStoredTheme()) return

    const query = window.matchMedia(DARK_QUERY)
    const onChange = () => setThemeState(systemTheme())
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const toggle = useCallback(() => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setThemeState(next)
  }, [theme])

  return { theme, toggle, isDark: theme === 'dark' }
}
