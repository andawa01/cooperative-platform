/**
 * Form primitives.
 *
 * Before this file each page carried its own copy of the label + input markup,
 * and they had already drifted (different heights, different focus rings). All
 * fields now come from here: one height, one focus treatment, one way to show a
 * hint and one way to show a required marker.
 */
import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

import { cn } from '@/lib/utils'

const CONTROL =
  'block w-full rounded-lg border border-input bg-card px-3 text-[15px] text-foreground ' +
  'shadow-xs transition-[border-color,box-shadow] duration-150 ' +
  'placeholder:text-stone-400 ' +
  'hover:border-stone-300 ' +
  'focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none ' +
  'disabled:cursor-not-allowed disabled:bg-stone-50 disabled:text-stone-500 ' +
  'aria-invalid:border-danger aria-invalid:ring-danger/15'

const inputClass = cn(CONTROL, 'h-11 py-2')

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  className,
  children,
}: {
  label: string
  htmlFor?: string
  hint?: ReactNode
  error?: ReactNode
  required?: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label
        htmlFor={htmlFor}
        className="flex items-center gap-1 text-sm font-medium text-stone-700"
      >
        {label}
        {required && (
          <span className="text-danger" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children}
      {hint && !error && (
        <p className="text-xs text-muted-foreground">{hint}</p>
      )}
      {error && <p className="text-xs font-medium text-danger-ink">{error}</p>}
    </div>
  )
}

export function TextInput({
  className,
  ...props
}: React.ComponentProps<'input'>) {
  return <input className={cn(inputClass, className)} {...props} />
}

export function TextArea({
  className,
  ...props
}: React.ComponentProps<'textarea'>) {
  return (
    <textarea
      className={cn(CONTROL, 'min-h-20 py-2.5 leading-relaxed', className)}
      {...props}
    />
  )
}

export function Select({
  className,
  children,
  ...props
}: React.ComponentProps<'select'>) {
  return (
    <div className="relative">
      <select
        className={cn(
          CONTROL,
          'h-11 cursor-pointer appearance-none py-2 pr-9',
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-stone-500"
        aria-hidden="true"
      />
    </div>
  )
}

/** Inline form-level error banner, used above the submit button. */
export function FormError({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
    >
      {children}
    </div>
  )
}

/** Field section title, used to break long forms into readable groups. */
export function FieldGroup({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <fieldset className="space-y-4">
      <legend className="sr-only">{title}</legend>
      <div>
        <h3 className="text-sm font-semibold text-stone-800">{title}</h3>
        {description && (
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        )}
      </div>
      {children}
    </fieldset>
  )
}
