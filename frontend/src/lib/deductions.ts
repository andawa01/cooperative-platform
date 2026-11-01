/**
 * Deduction reason labels, in one place.
 *
 * The backend keeps `reason_code` a closed set (D-031) so reports stay clean;
 * these are the human words for those codes. Kept out of the components
 * because three screens render the same list and they must agree — a clerk
 * filtering by "Cess" should see the rows the CSV also calls "Cess".
 */
import type { DeductionReason } from '@/types/api'

export const DEDUCTION_REASONS: DeductionReason[] = [
  'transport',
  'cess',
  'input_credit',
  'loan_recovery',
  'membership_fee',
  'withholding_tax',
  'fine',
  'other',
]

export const DEDUCTION_REASON_LABELS: Record<DeductionReason, string> = {
  transport: 'Transport',
  cess: 'Cess / levy',
  input_credit: 'Input credit',
  loan_recovery: 'Loan recovery',
  membership_fee: 'Membership fee',
  withholding_tax: 'Withholding tax',
  fine: 'Fine',
  other: 'Other',
}

/** One line of guidance per reason, shown in the record form. */
export const DEDUCTION_REASON_HINTS: Record<DeductionReason, string> = {
  transport: 'Haulage from the collection point to the store',
  cess: 'County levy or cooperative cess on the crop',
  input_credit: 'Recovery of seed, fertiliser or advance given on credit',
  loan_recovery: 'Instalment on a loan the cooperative issued',
  membership_fee: 'Annual or joining fee deducted at settlement',
  withholding_tax: 'Tax the cooperative withholds and remits',
  fine: 'Penalty agreed in the bylaws',
  other: 'Anything else — explain it in the reference or notes',
}

export function reasonLabel(reason: string): string {
  return DEDUCTION_REASON_LABELS[reason as DeductionReason] ?? reason
}
