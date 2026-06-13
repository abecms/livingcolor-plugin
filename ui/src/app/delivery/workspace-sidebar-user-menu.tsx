import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { LogIn } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'

export function WorkspaceSidebarUserMenu({
  collapsed = false
}: {
  collapsed?: boolean
}) {
  const { enabled, user, signOut } = useFirebaseAuth()

  if (!enabled || !user) {
    return null
  }

  const label = user.displayName || user.email || 'Account'

  const signOutButton = (
    <Button
      className={cn(
        'text-muted-foreground hover:text-foreground',
        collapsed ? 'size-9' : 'h-8 w-full justify-start px-2.5'
      )}
      onClick={() => void signOut()}
      size={collapsed ? 'icon' : 'sm'}
      title={collapsed ? 'Sign out' : undefined}
      type="button"
      variant="ghost"
    >
      <LogIn className="size-4 shrink-0" />
      {!collapsed ? <span className="text-sm">Sign out</span> : null}
    </Button>
  )

  if (collapsed) {
    return (
      <div className="space-y-1 border-t border-sidebar-border px-2 py-3">
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className="mx-auto flex size-9 items-center justify-center rounded-md text-xs font-medium text-muted-foreground"
              title={label}
            >
              {label.charAt(0).toUpperCase()}
            </div>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={8}>
            {label}
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>{signOutButton}</TooltipTrigger>
          <TooltipContent side="right" sideOffset={8}>
            Sign out
          </TooltipContent>
        </Tooltip>
      </div>
    )
  }

  return (
    <div className="space-y-1 border-t border-sidebar-border px-2 py-3">
      <p className="truncate px-2.5 text-sm font-medium text-sidebar-foreground" title={label}>
        {label}
      </p>
      {signOutButton}
    </div>
  )
}
