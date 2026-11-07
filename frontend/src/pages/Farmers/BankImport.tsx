import { useState } from 'react'
import { Loader2, Upload } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/common/Button'
import { Card, CardBody, CardHeader } from '@/components/common/Card'
import { PageHeader } from '@/components/common/PageHeader'
import { useImportBankDetails } from '@/hooks/useFarmers'
import type { BankDetailsImportResult } from '@/types/api'

const TEMPLATE =
  'phone,bank_name,bank_account_number\n0712345678,KCB,0123456789\n'

/**
 * Bulk bank details.
 *
 * Two steps on purpose. Checking the file writes nothing and reports every
 * row the server could not use, with the line number; applying writes only
 * the rows that matched. An import of payout destinations that says "12
 * saved" without saying what happened to the other three is an import that
 * gets trusted when it should not be.
 */
export default function BankDetailsImport() {
  const importMutation = useImportBankDetails()
  const [fileName, setFileName] = useState<string | null>(null)
  const [csv, setCsv] = useState('')
  const [preview, setPreview] = useState<BankDetailsImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onFile = async (file: File | null) => {
    setPreview(null)
    setError(null)
    setFileName(file?.name ?? null)
    if (!file) {
      setCsv('')
      return
    }
    try {
      setCsv(await file.text())
    } catch {
      setCsv('')
      setError('That file could not be read. Save it as CSV and try again.')
    }
  }

  const run = async (dryRun: boolean) => {
    setError(null)
    try {
      const result = await importMutation.mutateAsync({ csv, dry_run: dryRun })
      setPreview(result)
      if (!dryRun) {
        toast.success(
          `Bank details saved for ${result.applied} member${result.applied === 1 ? '' : 's'}`,
          {
            description:
              result.errors > 0
                ? `${result.errors} row${result.errors === 1 ? '' : 's'} skipped — see the list below.`
                : undefined,
          },
        )
      }
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const downloadTemplate = () => {
    const url = URL.createObjectURL(
      new Blob([TEMPLATE], { type: 'text/csv;charset=utf-8' }),
    )
    const link = document.createElement('a')
    link.href = url
    link.download = 'bank-details-template.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  const busy = importMutation.isPending

  return (
    <div>
      <PageHeader
        title="Import bank details"
        back={{ to: '/farmers', label: 'Farmers' }}
        description="Add or correct bank names and account numbers for many members from one CSV. Matching is by phone number, nobody is created, and no record changes until you apply."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="The file"
            description="A header row is required. Phone numbers can be local (07…) or international (+254…)."
          />
          <CardBody className="space-y-4">
            <pre className="overflow-x-auto rounded-lg border border-border bg-stone-50 p-3 text-xs leading-relaxed text-stone-700">
              {'phone,bank_name,bank_account_number\n0712345678,KCB,0123456789'}
            </pre>

            <div className="flex flex-wrap items-center gap-2">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium text-stone-700 shadow-xs transition-colors hover:bg-stone-50 focus-within:ring-4 focus-within:ring-primary-500/12">
                <Upload className="h-3.5 w-3.5" />
                Choose CSV
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="sr-only"
                  onChange={(e) => onFile(e.target.files?.[0] ?? null)}
                />
              </label>
              {fileName && (
                <span className="truncate text-sm text-stone-600">{fileName}</span>
              )}
              <Button type="button" size="sm" onClick={downloadTemplate}>
                Download template
              </Button>
            </div>

            {error && (
              <p
                role="alert"
                className="rounded-lg border border-danger/20 bg-danger-soft px-3 py-2 text-sm text-danger-ink"
              >
                {error}
              </p>
            )}

            <div className="flex flex-wrap justify-end gap-2 border-t border-border/60 pt-4">
              <Button onClick={() => run(true)} disabled={!csv || busy}>
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : null}
                {busy ? 'Checking…' : 'Check file'}
              </Button>
              {preview?.dry_run && preview.valid > 0 && (
                <Button
                  variant="primary"
                  onClick={() => run(false)}
                  disabled={busy}
                >
                  Apply {preview.valid} valid row
                  {preview.valid === 1 ? '' : 's'}
                </Button>
              )}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="What happens" />
          <CardBody className="space-y-2.5 text-sm text-stone-600">
            <p>
              Checking writes nothing. Every row comes back matched, or with the
              reason it cannot be used and the line it came from.
            </p>
            <p>
              Applying writes only the valid rows, in one transaction. Each
              member whose details change gets the same audit entry a manual
              edit would.
            </p>
            <p>
              Existing details are updated — that is how a wrong digit gets
              fixed. A member with no account is never created by this screen.
            </p>
          </CardBody>
        </Card>
      </div>

      {preview && (
        <Card className="mt-4">
          <CardHeader
            title={preview.dry_run ? 'Check result' : 'Import result'}
            description={`${preview.valid} ready, ${preview.errors} skipped${
              preview.dry_run ? '' : `, ${preview.applied} saved`
            } of ${preview.total} row${preview.total === 1 ? '' : 's'}`}
          />
          <CardBody>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-[11px] tracking-wider text-stone-500 uppercase">
                    <th className="py-2 pr-4 font-semibold">Line</th>
                    <th className="py-2 pr-4 font-semibold">Phone</th>
                    <th className="py-2 pr-4 font-semibold">Member</th>
                    <th className="py-2 pr-4 font-semibold">Status</th>
                    <th className="py-2 font-semibold">Note</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row) => (
                    <tr
                      key={row.line}
                      className="border-b border-border/50 last:border-0"
                    >
                      <td className="py-2 pr-4 text-stone-500 tabular-nums">
                        {row.line}
                      </td>
                      <td className="py-2 pr-4 text-stone-700 tabular-nums">
                        {row.phone}
                      </td>
                      <td className="py-2 pr-4 text-foreground">
                        {row.farmer_name ?? '—'}
                      </td>
                      <td className="py-2 pr-4">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${
                            row.status === 'error'
                              ? 'bg-danger-soft text-danger-ink'
                              : row.status === 'applied'
                                ? 'bg-success-soft text-success-ink'
                                : 'bg-primary-soft text-primary-ink'
                          }`}
                        >
                          {row.status === 'error'
                            ? 'Skipped'
                            : row.status === 'applied'
                              ? 'Saved'
                              : 'Ready'}
                        </span>
                      </td>
                      <td className="py-2 text-stone-600">{row.message ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
