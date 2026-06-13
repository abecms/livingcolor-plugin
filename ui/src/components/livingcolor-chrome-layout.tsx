import type { ReactNode } from 'react'

import { LivingColorSidebarBrand } from '@/components/livingcolor-logo'
import { cn } from '@/lib/utils'

/**
 * Minimal LivingColor chrome: brand sidebar + main content.
 * Used on Firebase setup/login before the full project workspace shell loads.
 */
export function LivingColorChromeLayout({
  children,
  className
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex h-full min-h-0 min-w-0 overflow-hidden', className)}>
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-card">
        <div className="flex min-h-[3.5rem] items-center border-b border-border px-4 py-3">
          <LivingColorSidebarBrand />
        </div>
      </aside>
      <main className="min-h-0 min-w-0 flex-1 overflow-auto">{children}</main>
    </div>
  )
}
