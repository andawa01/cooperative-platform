/**
 * Theme preference.
 *
 * Two states only: light and dark. The first visit follows the operating
 * system; once someone chooses explicitly, that choice wins forever (even if
 * their OS later changes) because they asked for it.
 *
 * The class is applied to `<html>` so the `.dark` token block in index.css
 * takes effect. `color-scheme` is set alongside it so native widgets — date
 * pickers, scrollbars, form controls — follow too, instead of staying bright
 * white inside a dark page.
 */
export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'shambatrack_theme'

const DARK_QUERY = '(prefers-color-scheme: dark)'

/** The preference this person saved, if they ever chose one. */
export function getStoredTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    // Storage can be blocked (private mode, hardened browser). Not fatal.
    return null
  }
}

export function systemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

/** Stored choice first, operating system second. */
export function resolveTheme(): Theme {
  return getStoredTheme() ?? systemTheme()
}

/** Apply a theme without remembering it (used for the initial paint). */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
}

/** Apply and remember. */
export function setTheme(theme: Theme): void {
  applyTheme(theme)
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // The theme still applies for this session even if it cannot be saved.
  }
}

export { DARK_QUERY }
