import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { LogIn, Settings, Users } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'

import { SETTINGS_ROUTE } from '../routes'

export function WorkspaceSidebarUserMenu({
  collapsed = false
}: {
  collapsed?: boolean
}) {
  const { enabled, user, signOut } = useFirebaseAuth()
  const label = user?.displayName || user?.email || 'Account'

  const trigger = (
    <Button
      className={cn(
        'justify-start font-normal text-sidebar-foreground',
        collapsed ? 'size-9' : 'h-9 w-full px-2.5'
      )}
      size={collapsed ? 'icon' : 'default'}
      title={collapsed ? label : undefined}
      variant="ghost"
    >
      <Users className="size-4 shrink-0" />
      {!collapsed ? <span className="min-w-0 flex-1 truncate text-left text-sm">{label}</span> : null}
    </Button>
  )

  const menu = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuItem asChild>
          <Link to={SETTINGS_ROUTE}>
            <Settings className="mr-2 size-4" />
            App settings
          </Link>
        </DropdownMenuItem>
        {enabled ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => void signOut()}>
              <LogIn className="mr-2 size-4" />
              Sign out
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )

  if (!collapsed) {
    return <div className="border-t border-sidebar-border px-2 py-3">{menu}</div>
  }

  return (
    <div className="border-t border-sidebar-border px-2 py-3">
      <Tooltip>
        <TooltipTrigger asChild>{menu}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {label}
        </TooltipContent>
      </Tooltip>
    </div>
  )
}
