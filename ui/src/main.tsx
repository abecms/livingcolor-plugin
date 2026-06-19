/**
 * Hermes dashboard plugin entry (dashboard/dist/index.js).
 *
 * Registers the LivingColor tab at /livingcolor and a header-right shell slot
 * for the project chat toggle. The chat terminal itself mounts inside the
 * plugin tab via ProjectWorkspaceSplit — not on the host /chat route.
 */
import { createRoot } from 'react-dom/client'
import { createElement } from 'react'
import App from './App'
import { installHermesNavBrand } from '@/lib/hermes-nav-brand'
import { findHermesPluginShell, syncLcRootToHermesHost } from '@/lib/hermes-host-layout'
import { isHermesPluginProjectDashboardPath } from '@/lib/hermes-plugin-routes'
import { PROJECT_CHAT_OPEN_CHANGED_EVENT } from '@/store/project-chat-layout'
import './styles.css'

const PLUGIN_NAME = 'livingcolor'
const CHAT_OPEN_STORAGE_KEY = 'livingcolor.projectChatOpen'

const SDK = (window as any).__HERMES_PLUGIN_SDK__
const REGISTRY = (window as any).__HERMES_PLUGINS__

function readProjectChatOpenFromStorage(): boolean {
  try {
    const raw = window.localStorage.getItem(CHAT_OPEN_STORAGE_KEY)
    if (raw === 'false') {
      return false
    }
    if (raw === 'true') {
      return true
    }
  } catch {
    // ignore
  }

  return true
}

function writeProjectChatOpenToStorage(open: boolean): void {
  try {
    window.localStorage.setItem(CHAT_OPEN_STORAGE_KEY, open ? 'true' : 'false')
  } catch {
    // ignore
  }
}

if (!SDK || !REGISTRY) {
  console.error(
    '[livingcolor] Hermes plugin SDK missing — register() was not called. ' +
      'Ensure the dashboard host loaded before this script.',
  )
}

if (SDK && REGISTRY) {
  const HostReact = SDK.React

  function LivingColorProjectChatShellToggle() {
    const { useState, useEffect } = SDK.hooks
    const [open, setOpen] = useState(readProjectChatOpenFromStorage)
    const [visible, setVisible] = useState(() => isHermesPluginProjectDashboardPath())

    useEffect(() => {
      const syncVisibility = () => setVisible(isHermesPluginProjectDashboardPath())
      const syncOpen = (event: Event) => {
        const detail = (event as CustomEvent<{ open?: boolean }>).detail
        setOpen(typeof detail?.open === 'boolean' ? detail.open : readProjectChatOpenFromStorage())
      }

      syncVisibility()
      window.addEventListener('popstate', syncVisibility)
      window.addEventListener(PROJECT_CHAT_OPEN_CHANGED_EVENT, syncOpen)
      const timer = window.setInterval(syncVisibility, 800)

      return () => {
        window.removeEventListener('popstate', syncVisibility)
        window.removeEventListener(PROJECT_CHAT_OPEN_CHANGED_EVENT, syncOpen)
        window.clearInterval(timer)
      }
    }, [])

    if (!visible) {
      return null
    }

    const Button = SDK.components.Button
    const label = open ? 'Close chat' : 'Open chat'

    return HostReact.createElement(
      Button,
      {
        type: 'button',
        variant: 'ghost',
        className: 'h-8 px-2 text-xs',
        title: label,
        'aria-label': label,
        onClick: () => {
          const next = !open
          writeProjectChatOpenToStorage(next)
          window.dispatchEvent(new CustomEvent(PROJECT_CHAT_OPEN_CHANGED_EVENT, { detail: { open: next } }))
          setOpen(next)
        }
      },
      label
    )
  }

  function LivingColorTab() {
    const ref = HostReact.useRef<HTMLDivElement | null>(null)
    HostReact.useEffect(() => {
      if (!ref.current) return
      const mount = createRoot(ref.current)
      mount.render(createElement(App))
      return () => mount.unmount()
    }, [])

    HostReact.useEffect(() => {
      const root = ref.current
      if (!root) return

      const update = () => syncLcRootToHermesHost(root)
      update()

      window.addEventListener('resize', update)
      const observer = new ResizeObserver(update)
      observer.observe(document.documentElement)
      const shell = findHermesPluginShell(root)
      if (shell) {
        observer.observe(shell.panel)
        observer.observe(shell.header)
      }

      return () => {
        window.removeEventListener('resize', update)
        observer.disconnect()
      }
    }, [])

    return HostReact.createElement('div', { ref, className: 'lc-root' })
  }

  REGISTRY.register(PLUGIN_NAME, LivingColorTab)

  if (typeof REGISTRY.registerSlot === 'function') {
    REGISTRY.registerSlot(PLUGIN_NAME, 'header-right', LivingColorProjectChatShellToggle)
  }

  installHermesNavBrand()
}
