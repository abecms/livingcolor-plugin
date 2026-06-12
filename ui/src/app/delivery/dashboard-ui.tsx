import type { ComponentProps, ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import type { IconComponent } from '@/lib/icons'
import { cn } from '@/lib/utils'

const DASHBOARD_NEUTRAL_CHROME =
  '[--ui-text-primary:rgba(255,255,255,0.92)] [--ui-text-secondary:rgba(255,255,255,0.68)] [--ui-text-tertiary:rgba(255,255,255,0.48)] [--dt-foreground:rgba(255,255,255,0.92)] [--color-foreground:rgba(255,255,255,0.92)]'

const DASHBOARD_PAGE_BACKGROUND = 'bg-[#101010]'
const DASHBOARD_INSET_X = 'px-6'

export function DashboardPageShell({
  children,
  className
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('relative flex h-full min-w-0 flex-col overflow-hidden', DASHBOARD_PAGE_BACKGROUND, DASHBOARD_NEUTRAL_CHROME, className)}>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(255,255,255,0.06),transparent_55%)]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.02)_0%,transparent_28%)]"
      />
      <div
        className={cn(
          'relative flex min-h-0 flex-1 flex-col overflow-hidden pb-10 pt-[calc(var(--titlebar-height)+1.25rem)]',
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
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-(--ui-text-secondary) backdrop-blur-sm">
          <span className="size-1.5 rounded-full bg-white/50" />
          {eyebrow}
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">{title}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/65">{description}</p>
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  )
}

const SECTION_ACCENTS = {
  default: 'from-white/10 to-white/[0.02] text-foreground',
  sprint: 'from-white/12 to-white/[0.03] text-foreground',
  active: 'from-white/12 to-white/[0.03] text-foreground',
  success: 'from-white/12 to-white/[0.03] text-foreground',
  warning: 'from-white/12 to-white/[0.03] text-foreground'
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
    <section className="overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.025] shadow-[0_20px_60px_-40px_rgba(0,0,0,0.85)] backdrop-blur-sm">
      <div className="flex items-start gap-3 border-b border-white/[0.06] px-5 py-4">
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
          {description ? <p className="mt-1 text-sm text-(--ui-text-secondary)">{description}</p> : null}
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
    default: 'border-white/10 bg-white/[0.03]',
    active: 'border-white/12 bg-white/[0.04]',
    success: 'border-white/12 bg-white/[0.04]'
  } as const

  const labelStyles = {
    default: 'text-(--ui-text-tertiary)',
    active: 'text-(--ui-text-secondary)',
    success: 'text-(--ui-text-secondary)'
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
    warning: 'text-(--ui-text-secondary)',
    neutral: 'text-foreground'
  } as const

  return (
    <div className="rounded-xl border border-white/[0.06] bg-black/10 px-4 py-3">
      <div className="text-xs text-(--ui-text-tertiary)">{label}</div>
      <div className={cn('mt-1 text-lg font-semibold tabular-nums tracking-tight', valueTone[tone])}>{value}</div>
    </div>
  )
}

export function SprintProgressBar({ capacity, used }: { capacity: number; used: number }) {
  const safeCapacity = Math.max(capacity, 0.0001)
  const pct = Math.min(100, Math.round((used / safeCapacity) * 100))
  const tone =
    pct >= 95 ? 'from-white/35 to-white/55' : pct >= 80 ? 'from-white/45 to-white/65' : 'from-white/55 to-white/80'

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-(--ui-text-secondary)">
        <span>Sprint load</span>
        <span className="font-medium tabular-nums text-foreground">{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/10">
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
    good: 'border-white/15 bg-white/[0.06] text-foreground',
    warning: 'border-white/12 bg-white/[0.04] text-(--ui-text-secondary)',
    neutral: 'border-white/10 bg-white/[0.05] text-(--ui-text-secondary)'
  } as const

  return (
    <span className={cn('inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium', styles[tone])}>
      {children}
    </span>
  )
}

export function TicketKeyBadge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border border-white/10 bg-white/[0.04] px-2 py-0.5 font-mono text-[11px] font-medium text-(--ui-text-secondary)">
      {children}
    </span>
  )
}

export function ProseBlock({ children }: { children: ReactNode }) {
  return (
    <div className="mt-3 max-h-40 overflow-auto rounded-xl border border-white/[0.06] bg-black/20 p-3 text-xs leading-relaxed text-(--ui-text-secondary) whitespace-pre-wrap">
      {children}
    </div>
  )
}

export function DashboardEmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-8 text-center text-sm text-(--ui-text-secondary)">
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
  return {
    className:
      '!border-white/20 !bg-white/[0.06] !text-white shadow-none hover:!border-white/30 hover:!bg-white/10 dark:!border-white/20 dark:!bg-white/[0.06] dark:!text-white dark:hover:!border-white/30 dark:hover:!bg-white/10',
    variant: 'outline' as const
  }
}

export function dashboardOutlineButtonProps() {
  return {
    className:
      '!border-white/15 !bg-transparent !text-white/65 shadow-none hover:!border-white/25 hover:!bg-white/5 hover:!text-white dark:!border-white/15 dark:!bg-transparent dark:!text-white/65 dark:hover:!border-white/25 dark:hover:!bg-white/5 dark:hover:!text-white',
    variant: 'outline' as const
  }
}

export function DashboardGhostButton({
  children,
  ...props
}: ComponentProps<typeof Button>) {
  return (
    <Button
      className="!border-white/15 !bg-white/[0.04] !text-white hover:!bg-white/[0.08] dark:!border-white/15 dark:!bg-white/[0.04] dark:!text-white dark:hover:!bg-white/[0.08]"
      size="sm"
      variant="outline"
      {...props}
    >
      {children}
    </Button>
  )
}
