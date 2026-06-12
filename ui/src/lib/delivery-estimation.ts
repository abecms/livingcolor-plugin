/** Person-day estimates from delivery runtime are converted to hours for PM review. */

export const HOURS_PER_PERSON_DAY = 7

export function personDaysToHours(estimatedDays: number): number {
  return Math.round(estimatedDays * HOURS_PER_PERSON_DAY * 10) / 10
}

export function formatTicketEstimationHours(estimatedDays: number | null | undefined): string | null {
  if (estimatedDays == null || !Number.isFinite(estimatedDays)) {
    return null
  }

  const hours = personDaysToHours(estimatedDays)
  const formatted = Number.isInteger(hours) ? String(hours) : hours.toFixed(1)
  return `${formatted} h`
}
