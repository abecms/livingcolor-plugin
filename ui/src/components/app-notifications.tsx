import { useStore } from '@nanostores/react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { dismissNotification, $notifications } from '@/store/notifications'

const KIND_STYLES = {
  error: 'border-red-500/40 bg-red-500/10 text-red-100',
  warning: 'border-amber-500/40 bg-amber-500/10 text-amber-100',
  info: 'border-sky-500/40 bg-sky-500/10 text-sky-100',
  success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
} as const

export function AppNotifications() {
  const notifications = useStore($notifications)

  if (notifications.length === 0) {
    return null
  }

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-full max-w-sm flex-col gap-2 px-4">
      {notifications.map(notification => (
        <div
          className={cn(
            'pointer-events-auto rounded-lg border px-3 py-2 text-sm shadow-lg backdrop-blur-sm',
            KIND_STYLES[notification.kind]
          )}
          key={notification.id}
          role="status"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              {notification.title ? (
                <div className="font-medium text-foreground">{notification.title}</div>
              ) : null}
              <div className="text-foreground/90">{notification.message}</div>
              {notification.detail ? (
                <div className="text-xs text-(--ui-text-secondary)">{notification.detail}</div>
              ) : null}
            </div>
            <Button
              className="h-7 shrink-0 px-2 text-xs"
              onClick={() => dismissNotification(notification.id)}
              size="sm"
              type="button"
              variant="ghost"
            >
              Dismiss
            </Button>
          </div>
        </div>
      ))}
    </div>
  )
}
