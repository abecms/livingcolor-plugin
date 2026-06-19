import { useStore } from '@nanostores/react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import { isProjectWorkspacePath, parseProjectKeyFromPath } from './project-navigation'
import { ProjectChatPanel, useProjectChatPanelWidth } from './project-chat-panel'
import { $projectChatOpen, setProjectChatOpen } from '@/store/project-chat-layout'

export function ProjectWorkspaceSplit({ children }: { children: ReactNode }) {
  const location = useLocation()
  const chatOpen = useStore($projectChatOpen)
  const widthPx = useProjectChatPanelWidth()
  const projectKey = parseProjectKeyFromPath(location.pathname)
  const showChat = Boolean(
    chatOpen && projectKey && isProjectWorkspacePath(location.pathname) && parseProjectKeyFromPath(location.pathname)
  )

  return (
    <div className="flex h-full min-h-0 min-w-0 overflow-hidden">
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</div>
      {showChat && projectKey ? (
        <ProjectChatPanel onClose={() => setProjectChatOpen(false)} projectKey={projectKey} widthPx={widthPx} />
      ) : null}
    </div>
  )
}
