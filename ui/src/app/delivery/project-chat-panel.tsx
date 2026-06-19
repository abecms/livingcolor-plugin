import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useState, type PointerEvent as ReactPointerEvent } from 'react'

import { HermesChatTerminal } from '@/components/hermes-chat-terminal'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { Plus, RefreshCw, X } from '@/lib/icons'
import {
  clearProjectChatSessionId,
  discoverProjectChatSessionId,
  getProjectChatSessionId
} from '@/lib/project-chat-session'
import {
  PROJECT_CHAT_MAX_WIDTH_PX,
  PROJECT_CHAT_MIN_WIDTH_PX,
  setProjectChatWidthPx,
  $projectChatWidthPx
} from '@/store/project-chat-layout'

export interface ProjectChatPanelProps {
  onClose: () => void
  projectKey: string
  widthPx: number
}

export function ProjectChatPanel({ onClose, projectKey, widthPx }: ProjectChatPanelProps) {
  const { t } = useI18n()
  const [mountKey, setMountKey] = useState('initial')
  const [resumeSessionId, setResumeSessionId] = useState<string | null>(() => getProjectChatSessionId(projectKey))
  const [sessionProbeReady, setSessionProbeReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    setSessionProbeReady(false)
    setResumeSessionId(getProjectChatSessionId(projectKey))

    void discoverProjectChatSessionId(projectKey).then(sessionId => {
      if (cancelled) {
        return
      }
      if (sessionId) {
        setResumeSessionId(sessionId)
      }
      setSessionProbeReady(true)
    })

    return () => {
      cancelled = true
    }
  }, [projectKey, mountKey])

  const startFreshWorkstream = useCallback(() => {
    clearProjectChatSessionId(projectKey)
    setMountKey(`fresh-${Date.now()}`)
  }, [projectKey])

  const handleResizePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault()

      const startX = event.clientX
      const startWidth = widthPx

      const onMove = (moveEvent: PointerEvent) => {
        const delta = startX - moveEvent.clientX
        setProjectChatWidthPx(startWidth + delta)
      }

      const onUp = () => {
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }

      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
    },
    [widthPx]
  )

  return (
    <aside
      className="relative flex h-full min-h-0 shrink-0 flex-col border-l border-border bg-card"
      style={{
        width: `${Math.min(PROJECT_CHAT_MAX_WIDTH_PX, Math.max(PROJECT_CHAT_MIN_WIDTH_PX, widthPx))}px`
      }}
    >
      <div
        aria-orientation="vertical"
        className="absolute inset-y-0 left-0 z-10 w-1 -translate-x-1/2 cursor-col-resize hover:bg-ring/40"
        onPointerDown={handleResizePointerDown}
        role="separator"
      />

      <header className="flex h-10 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
        <span className="truncate text-xs font-medium text-muted-foreground">
          {t.shell.projectChatTitle} · {projectKey}
        </span>
        <div className="flex items-center gap-1">
          <Button
            aria-label={t.shell.projectChatNew}
            className="size-7"
            onClick={startFreshWorkstream}
            title={t.shell.projectChatNew}
            type="button"
            variant="ghost"
          >
            <Plus className="size-3.5" />
          </Button>
          <Button
            aria-label={t.shell.projectChatReset}
            className="size-7"
            onClick={startFreshWorkstream}
            title={t.shell.projectChatReset}
            type="button"
            variant="ghost"
          >
            <RefreshCw className="size-3.5" />
          </Button>
          <Button
            aria-label={t.shell.projectChatClose}
            className="size-7"
            onClick={onClose}
            title={t.shell.projectChatClose}
            type="button"
            variant="ghost"
          >
            <X className="size-3.5" />
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {sessionProbeReady ? (
          <HermesChatTerminal
            key={`${projectKey}:${mountKey}`}
            mountKey={mountKey}
            projectKey={projectKey}
            resumeSessionId={resumeSessionId}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center px-4 text-xs text-muted-foreground">
            {t.shell.projectChatLoading}
          </div>
        )}
      </div>
    </aside>
  )
}

export function useProjectChatPanelWidth(): number {
  return useStore($projectChatWidthPx)
}
