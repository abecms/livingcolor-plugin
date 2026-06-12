import type { ReactNode } from 'react'

import type { IconComponent } from '@/lib/icons'
import { cn } from '@/lib/utils'

import { PAGE_INSET_X } from './layout-constants'

export function ManagerPageShell({
  bottomPanel,
  children,
  wide = false
}: {
  bottomPanel?: ReactNode
  children: ReactNode
  wide?: boolean
}) {
  return (
    <section className="flex h-full min-w-0 flex-col overflow-hidden bg-(--ui-chat-surface-background)">
      <div className={cn('min-h-0 flex-1 overflow-y-auto pb-8 pt-[calc(var(--titlebar-height)+1rem)]', PAGE_INSET_X)}>
        <div className={cn('mx-auto flex w-full flex-col gap-10', wide ? 'max-w-none' : 'max-w-4xl')}>{children}</div>
      </div>
      {bottomPanel}
    </section>
  )
}

export function ManagerPageHeader({
  actions,
  description,
  eyebrow,
  icon: Icon,
  title
}: {
  actions?: ReactNode
  description: string
  eyebrow: string
  icon: IconComponent
  title: string
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-(--ui-text-tertiary)">
          <Icon className="size-4" />
          {eyebrow}
        </div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-(--ui-text-secondary)">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
  )
}

export function toneClass(tone?: 'good' | 'neutral' | 'warning') {
  switch (tone) {
    case 'good':
      return 'text-emerald-300'

    case 'warning':
      return 'text-amber-300'

    default:
      return 'text-foreground'
  }
}

export function ManagerMetricList({
  items
}: {
  items: readonly { detail: string; label: string; tone?: 'good' | 'neutral' | 'warning'; value: string }[]
}) {
  return (
    <dl className="divide-y divide-(--ui-stroke-tertiary) border-y border-(--ui-stroke-tertiary)">
      {items.map(item => (
        <div className="flex items-baseline justify-between gap-6 py-3.5" key={item.label}>
          <div className="min-w-0">
            <dt className="text-sm font-medium text-foreground">{item.label}</dt>
            <dd className="mt-1 text-sm text-(--ui-text-secondary)">{item.detail}</dd>
          </div>
          <dd className={cn('shrink-0 text-base font-semibold tabular-nums', toneClass(item.tone))}>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function ManagerSection({
  children,
  icon: Icon,
  title
}: {
  children: ReactNode
  icon: IconComponent
  title: string
}) {
  return (
    <section>
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
        <Icon className="size-4 text-(--ui-text-tertiary)" />
        {title}
      </div>
      <div className="divide-y divide-(--ui-stroke-tertiary) border-y border-(--ui-stroke-tertiary)">{children}</div>
    </section>
  )
}

export function ManagerListRow({ description, title }: { description?: string; title: string }) {
  return (
    <div className="py-3.5">
      <div className="text-sm font-medium text-foreground">{title}</div>
      {description ? <p className="mt-1 text-sm leading-relaxed text-(--ui-text-secondary)">{description}</p> : null}
    </div>
  )
}
