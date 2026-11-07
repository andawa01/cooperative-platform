/**
 * Styled confirmation dialog for consequential actions.
 *
 * Wraps a native <dialog> so focus trapping, Escape-to-close and the
 * backdrop come from the browser instead of a dependency. Escape and
 * backdrop clicks route through `onClose` so the caller's state stays in
 * sync with what is actually on screen.
 */
import { useEffect, useRef, type ReactNode } from 'react'

import { Button } from './Button'

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  tone = 'primary',
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel: string
  tone?: 'primary' | 'danger'
  busy?: boolean
  onConfirm: () => void | Promise<void>
  onClose: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-label={title}
      // Escape fires cancel before close, so the caller learns about it here.
      onCancel={onClose}
      // With the dialog padding-free, a click that lands on the element
      // itself came from the backdrop.
      onClick={(event) => {
        if (event.target === ref.current) onClose()
      }}
      className="m-auto w-[min(92vw,26rem)] rounded-card border border-border/80 bg-card p-0 text-foreground shadow-lift backdrop:bg-black/40 backdrop:backdrop-blur-[2px]"
    >
      <div className="p-5">
        <h2 className="text-[15px] font-semibold text-foreground">{title}</h2>
        <div className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
          {description}
        </div>
        <div className="mt-5 flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant={tone}
            onClick={() => void onConfirm()}
            disabled={busy}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  )
}
