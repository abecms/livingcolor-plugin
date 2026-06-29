import type { PmInboxPayload } from '@/lib/delivery'

type SprintTicket = PmInboxPayload['selectedSprint'] extends infer Sprint
  ? Sprint extends { tickets: Array<infer Ticket> }
    ? Ticket
    : never
  : never

export function ticketCountsTowardSprintCapacity(ticket: SprintTicket): boolean {
  if (ticket.inDevelopment) {
    if (ticket.sprintSelected != null) {
      return ticket.sprintSelected
    }
    return (ticket.readinessStatus ?? '').trim().toLowerCase() === 'ready'
  }
  return (ticket.readinessStatus ?? 'ready').trim().toLowerCase() === 'ready'
}

export function computeSprintUsedDays(tickets: SprintTicket[]): number {
  const total = tickets.reduce((sum, ticket) => {
    if (!ticketCountsTowardSprintCapacity(ticket)) {
      return sum
    }
    return sum + (ticket.estimatedDays ?? 0)
  }, 0)
  return Math.round(total * 100) / 100
}
