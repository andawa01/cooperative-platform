/**
 * App-level button styles.
 *
 * Everything interactive in the app uses this file instead of the unused
 * shadcn scaffolding in components/ui, so a button looks the same on every
 * screen. Variants describe intent, not colour: `primary` is the one action a
 * page is asking you to take, `secondary` is an alternative, `danger` is
 * destructive and always asks first.
 */
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
export type ButtonSize = 'sm' | 'md' | 'lg'

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap ' +
  'transition-[background-color,border-color,color,box-shadow,transform] duration-150 ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 focus-visible:ring-offset-2 ' +
  'focus-visible:ring-offset-background active:translate-y-px ' +
  'disabled:pointer-events-none disabled:opacity-55'

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-primary-600 text-white shadow-xs hover:bg-primary-700 active:bg-primary-800',
  secondary:
    'border border-stone-200 bg-card text-stone-700 shadow-xs hover:border-stone-300 hover:bg-stone-50 hover:text-stone-900',
  danger:
    'border border-danger/25 bg-card text-danger-ink shadow-xs hover:border-danger/40 hover:bg-danger-soft',
  ghost: 'text-stone-600 hover:bg-stone-100 hover:text-stone-900',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-[13px]',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-[15px]',
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
