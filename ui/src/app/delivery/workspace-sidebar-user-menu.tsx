import { Link, useLocation } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { LogIn, Settings } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'
import { SETTINGS_ROUTE } from '../routes'

import { isGlobalSettingsPath } from './project-navigation'

function FooterAction({
  active,
  collapsed,
  href,
  icon: Icon,
  label
}: {
  active?: boolean
  collapsed: boolean
  href?: string
  icon: typeof Settings
  label: string
  onClick?: () => void
}) {
  const className = cn(
    'text-muted-foreground hover:text-foreground',
    collapsed ? 'size-9' : 'h-8 w-full justify-start px-2.5',
    active && 'bg-accent text-foreground'
  )

  const content = href ? (
    <Button asChild className={className} size={collapsed ? 'icon' : 'sm'} variant="ghost">
      <Link title={collapsed ? label : undefined} to={href}>
        <Icon className="size-4 shrink-0" />
        {!collapsed ? <span className="text-sm">{label}</span> : null}
      </Link>
    </Button>
  ) : (
    <Button className={className} size={collapsed ? 'icon' : 'sm'} title={collapsed ? label : undefined} type="button" variant="ghost">
      <Icon className="size-4 shrink-0" />
      {!collapsed ? <span className="text-sm">{label}</span> : null}
    </Button>
  )

  if (!collapsed) {
    return content
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {label}
      </TooltipContent>
    </Tooltip>
  )
}

export function WorkspaceSidebarUserMenu({
  collapsed = false
}: {
  collapsed?: boolean
}) {
  const location = useLocation()
  const { enabled, user, signOut } = useFirebaseAuth()
  const settingsActive = isGlobalSettingsPath(location.pathname)
  const label = user?.displayName || user?.email || 'Account'

  const settingsAction = (
    <FooterAction
      active={settingsActive}
      collapsed={collapsed}
      href={SETTINGS_ROUTE}
      icon={Settings}
      label="Settings"
    />
  )

  const signOutAction = enabled && user ? (
    collapsed ? (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            className="size-9 text-muted-foreground hover:text-foreground"
            onClick={() => void signOut()}
            size="icon"
            title="Sign out"
            type="button"
            variant="ghost"
          >
            <LogIn className="size-4 shrink-0" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          Sign out
        </TooltipContent>
      </Tooltip>
    ) : (
      <Button
        className="h-8 w-full justify-start px-2.5 text-muted-foreground hover:text-foreground"
        onClick={() => void signOut()}
        size="sm"
        type="button"
        variant="ghost"
      >
        <LogIn className="size-4 shrink-0" />
        <span className="text-sm">Sign out</span>
      </Button>
    )
  ) : null

  if (collapsed) {
    return (
      <div className="space-y-1 border-t border-sidebar-border px-2 py-3">
        {enabled && user ? (
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
        ) : null}
        {settingsAction}
        {signOutAction}
      </div>
    )
  }

  return (
    <div className="space-y-1 border-t border-sidebar-border px-2 py-3">
      {enabled && user ? (
        <p className="truncate px-2.5 text-sm font-medium text-sidebar-foreground" title={label}>
          {label}
        </p>
      ) : null}
      {settingsAction}
      {signOutAction}
    </div>
  )
}
