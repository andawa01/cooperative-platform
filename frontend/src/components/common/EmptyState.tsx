export function EmptyState({
  title,
  description,
  action,
  bordered = true,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  /** Set false when rendered inside a table body, which already has a border. */
  bordered?: boolean
}) {
  return (
    <div
      className={
        bordered
          ? 'flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white px-6 py-12 text-center'
          : 'flex flex-col items-center justify-center px-6 py-12 text-center'
      }
    >
      <h3 className="text-base font-semibold text-gray-900">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-gray-600">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}