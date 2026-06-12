import type { ComponentProps, ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import type { IconComponent } from '@/lib/icons'
import { cn } from '@/lib/utils'

const DASHBOARD_INSET_X = 'px-6'

export function DashboardPageShell({
  children,
  className
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('relative flex h-full min-w-0 flex-col overflow-hidden', className)}>
      <div
        className={cn(
          'relative flex min-h-0 flex-1 flex-col overflow-hidden pb-10 pt-6',
          DASHBOARD_INSET_X
        )}
      >
        <div className="flex h-full w-full min-h-0 flex-col gap-8">{children}</div>
      </div>
    </section>
  )
}

export function DashboardPageHeader({
  actions,
  description,
  eyebrow,
  title
}: {
  actions?: ReactNode
  description: string
  eyebrow: string
  title: string
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-5">
      <div className="min-w-0 space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
          <span className="size-1.5 rounded-full bg-muted-foreground" />
          {eyebrow}
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p>
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  )
}

const SECTION_ACCENTS = {
  default: 'from-muted to-muted/30 text-foreground',
  sprint: 'from-primary/15 to-primary/5 text-foreground',
  active: 'from-primary/15 to-primary/5 text-foreground',
  success: 'from-primary/15 to-primary/5 text-foreground',
  warning: 'from-warning/20 to-warning/5 text-foreground'
} as const

export function DashboardSection({
  accent = 'default',
  children,
  description,
  icon: Icon,
  title
}: {
  accent?: keyof typeof SECTION_ACCENTS
  children: ReactNode
  description?: string
  icon: IconComponent
  title: string
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
      <div className="flex items-start gap-3 border-b border-border px-5 py-4">
        <div
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br shadow-inner',
            SECTION_ACCENTS[accent]
          )}
        >
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 pt-0.5">
          <h2 className="text-base font-semibold tracking-tight text-foreground">{title}</h2>
          {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
        </div>
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}

export function DashboardHighlightCard({
  accent = 'default',
  children,
  label
}: {
  accent?: 'default' | 'active' | 'success'
  children: ReactNode
  label: string
}) {
  const styles = {
    default: 'border-border bg-muted/40',
    active: 'border-border bg-muted/60',
    success: 'border-border bg-muted/60'
  } as const

  const labelStyles = {
    default: 'text-muted-foreground',
    active: 'text-muted-foreground',
    success: 'text-muted-foreground'
  } as const

  return (
    <div className={cn('rounded-xl border p-4', styles[accent])}>
      <div className={cn('text-[11px] font-medium uppercase tracking-[0.14em]', labelStyles[accent])}>{label}</div>
      <div className="mt-3">{children}</div>
    </div>
  )
}

export function DashboardStatGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{children}</div>
}

export function DashboardStat({
  label,
  tone = 'neutral',
  value
}: {
  label: string
  tone?: 'good' | 'neutral' | 'warning'
  value: string
}) {
  const valueTone = {
    good: 'text-foreground',
    warning: 'text-muted-foreground',
    neutral: 'text-foreground'
  } as const

  return (
    <div className="rounded-xl border border-border bg-muted/30 px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 text-lg font-semibold tabular-nums tracking-tight', valueTone[tone])}>{value}</div>
    </div>
  )
}

export function SprintProgressBar({ capacity, used }: { capacity: number; used: number }) {
  const safeCapacity = Math.max(capacity, 0.0001)
  const pct = Math.min(100, Math.round((used / safeCapacity) * 100))
  const tone =
    pct >= 95 ? 'from-warning/70 to-warning' : pct >= 80 ? 'from-primary/50 to-primary/80' : 'from-primary/70 to-primary'

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Sprint load</span>
        <span className="font-medium tabular-nums text-foreground">{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full bg-gradient-to-r transition-all duration-500', tone)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export function StatusPill({
  children,
  tone = 'neutral'
}: {
  children: ReactNode
  tone?: 'good' | 'neutral' | 'warning'
}) {
  const styles = {
    good: 'border-border bg-muted/50 text-foreground',
    warning: 'border-border bg-muted/40 text-muted-foreground',
    neutral: 'border-border bg-muted/40 text-muted-foreground'
  } as const

  return (
    <span className={cn('inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium', styles[tone])}>
      {children}
    </span>
  )
}

export function TicketKeyBadge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border border-border bg-card px-2 py-0.5 font-mono text-[11px] font-medium text-muted-foreground">
      {children}
    </span>
  )
}

export function ProseBlock({ children }: { children: ReactNode }) {
  return (
    <div className="mt-3 max-h-40 overflow-auto rounded-xl border border-border bg-muted/50 p-3 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
      {children}
    </div>
  )
}

export function DashboardEmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground">
      {children}
    </div>
  )
}

export function DashboardActionRow({ children }: { children: ReactNode }) {
  return <div className="mt-4 flex flex-wrap gap-2">{children}</div>
}

export const DASHBOARD_SHEET_HEADER_CLASS = 'px-6 pt-6'
export const DASHBOARD_SHEET_BODY_CLASS = 'mt-4 space-y-5 px-6 pb-6'

export function dashboardPrimaryButtonProps() {
  return { variant: 'default' as const }
}

export function dashboardOutlineButtonProps() {
  return { variant: 'outline' as const }
}

export function DashboardGhostButton({
  children,
  ...props
}: ComponentProps<typeof Button>) {
  return (
    <Button size="sm" variant="outline" {...props}>
      {children}
    </Button>
  )
}
