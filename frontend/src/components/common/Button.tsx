/**
 * App-level button styles.
 *
 * The shadcn primitives in components/ui are unused scaffolding (they import
 * `cn` from an unrelated npm package). Everything interactive in the app uses
 * this file instead, so a button looks the same on every screen.
 */
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
export type ButtonSize = 'sm' | 'md'

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap transition ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 ' +
  'disabled:pointer-events-none disabled:opacity-50'

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-primary-600 text-white hover:bg-primary-700',
  secondary:
    'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 hover:text-gray-900',
  danger: 'border border-red-300 bg-white text-red-700 hover:bg-red-50',
  ghost: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
}

function buttonClass(
  variant: ButtonVariant = 'secondary',
  size: ButtonSize = 'md',
  className?: string,
) {
  return cn(BASE, VARIANTS[variant], SIZES[size], className)
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  ...props
}: React.ComponentProps<'button'> & {
  variant?: ButtonVariant
  size?: ButtonSize
}) {
  return (
    <button
      type="button"
      className={buttonClass(variant, size, className)}
      {...props}
    />
  )
}

export function ButtonLink({
  to,
  variant = 'secondary',
  size = 'md',
  className,
  children,
  icon,
}: {
  to: string
  variant?: ButtonVariant
  size?: ButtonSize
  className?: string
  children: ReactNode
  icon?: ReactNode
}) {
  return (
    <Link to={to} className={buttonClass(variant, size, className)}>
      {icon}
      {children}
    </Link>
  )
}
