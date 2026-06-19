import { FitAddon } from '@xterm/addon-fit'
import { Unicode11Addon } from '@xterm/addon-unicode11'
import { WebglAddon } from '@xterm/addon-webgl'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useEffect, useMemo, useRef, useState } from 'react'

import { buildHermesPtyWebSocketUrl } from '@/lib/hermes-plugin-sdk'
import {
  HERMES_TERMINAL_THEME_STATIC,
  useHermesTerminalBackground
} from '@/lib/hermes-terminal-theme'
import {
  extractProjectChatSessionId,
  persistProjectChatSession,
  resolveProjectChatResumeSessionId
} from '@/lib/project-chat-session'
import { cn } from '@/lib/utils'

// xterm.js emits SGR mouse reports that must not be forwarded to the PTY.
// eslint-disable-next-line no-control-regex
const SGR_MOUSE_RE = /^\x1b\[<(\d+);(\d+);(\d+)([Mm])$/

function generateChannelId(projectKey: string): string {
  const key = projectKey.trim().toUpperCase()
  const suffix =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`

  return `lc-${key}-${suffix}`
}

export interface HermesChatTerminalProps {
  className?: string
  mountKey: string
  projectKey: string
  resumeSessionId?: string | null
}

export function HermesChatTerminal({ className, mountKey, projectKey, resumeSessionId }: HermesChatTerminalProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const termRef = useRef<Terminal | null>(null)
  const terminalBackground = useHermesTerminalBackground()
  const terminalTheme = useMemo(
    () => ({ ...HERMES_TERMINAL_THEME_STATIC, background: terminalBackground }),
    [terminalBackground]
  )
  const [banner, setBanner] = useState<string | null>(null)
  const [effectiveResume, setEffectiveResume] = useState<string | null>(null)
  const [resumeReady, setResumeReady] = useState(!resumeSessionId)
  const persistedSessionIdRef = useRef<string | null>(null)
  const channel = useMemo(() => generateChannelId(projectKey), [mountKey, projectKey])

  useEffect(() => {
    let cancelled = false

    if (!resumeSessionId) {
      setEffectiveResume(null)
      setResumeReady(true)
      return () => {
        cancelled = true
      }
    }

    setResumeReady(false)
    void resolveProjectChatResumeSessionId(projectKey, resumeSessionId).then(sessionId => {
      if (!cancelled) {
        setEffectiveResume(sessionId)
        setResumeReady(true)
      }
    })

    return () => {
      cancelled = true
    }
  }, [resumeSessionId, mountKey, projectKey])

  useEffect(() => {
    persistedSessionIdRef.current = null
  }, [mountKey, projectKey])

  useEffect(() => {
    const term = termRef.current
    if (!term) {
      return
    }

    term.options.theme = terminalTheme
  }, [terminalTheme])

  useEffect(() => {
    const host = hostRef.current
    if (!host || !resumeReady) {
      return
    }

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: 'JetBrains Mono, ui-monospace, monospace',
      fontSize: 12,
      lineHeight: 1.15,
      theme: terminalTheme,
      allowProposedApi: true
    })
    termRef.current = term

    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new Unicode11Addon())
    term.unicode.activeVersion = '11'

    let webglAddon: WebglAddon | null = null
    try {
      webglAddon = new WebglAddon()
      term.loadAddon(webglAddon)
    } catch {
      webglAddon = null
    }

    term.open(host)

    let ws: WebSocket | null = null
    let unmounting = false
    let onDataDisposable: { dispose(): void } | null = null
    let onResizeDisposable: { dispose(): void } | null = null

    const syncFit = () => {
      fit.fit()
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(`\x1b[RESIZE:${term.cols};${term.rows}]`)
      }
    }

    const resizeObserver = new ResizeObserver(() => {
      window.requestAnimationFrame(syncFit)
    })
    resizeObserver.observe(host)
    window.addEventListener('resize', syncFit)

    void (async () => {
      try {
        const url = await buildHermesPtyWebSocketUrl({
          channel,
          livingcolorProjectKey: projectKey,
          resumeSessionId: effectiveResume
        })
        if (unmounting) {
          return
        }

        ws = new WebSocket(url)
        ws.binaryType = 'arraybuffer'

        ws.onopen = () => {
          setBanner(null)
          syncFit()
        }

        ws.onmessage = event => {
          const chunk =
            typeof event.data === 'string'
              ? event.data
              : new TextDecoder().decode(event.data as ArrayBuffer)

          const sessionId = extractProjectChatSessionId(chunk)
          if (sessionId && persistedSessionIdRef.current !== sessionId) {
            persistedSessionIdRef.current = sessionId
            void persistProjectChatSession(projectKey, sessionId)
          }

          if (typeof event.data === 'string') {
            term.write(event.data)
            return
          }

          term.write(new Uint8Array(event.data as ArrayBuffer))
        }

        ws.onclose = event => {
          if (unmounting) {
            return
          }

          if (event.code === 4401) {
            setBanner('Auth failed. Reload the dashboard to refresh your session.')
            return
          }

          term.write(`\r\n\x1b[90m[session ended (code ${event.code})]\x1b[0m\r\n`)
        }

        onDataDisposable = term.onData(data => {
          if (!ws || ws.readyState !== WebSocket.OPEN || SGR_MOUSE_RE.test(data)) {
            return
          }

          ws.send(data)
        })

        onResizeDisposable = term.onResize(({ cols, rows }) => {
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(`\x1b[RESIZE:${cols};${rows}]`)
          }
        })
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Could not connect to Hermes chat.'
        setBanner(message)
      }
    })()

    window.requestAnimationFrame(syncFit)

    return () => {
      unmounting = true
      termRef.current = null
      onDataDisposable?.dispose()
      onResizeDisposable?.dispose()
      resizeObserver.disconnect()
      window.removeEventListener('resize', syncFit)
      ws?.close()
      webglAddon?.dispose()
      term.dispose()
    }
  }, [channel, effectiveResume, mountKey, projectKey, resumeReady])

  return (
    <div className={cn('flex min-h-0 min-w-0 flex-1 flex-col', className)}>
      {banner ? (
        <div className="border-b border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">{banner}</div>
      ) : null}
      <div
        className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg p-2"
        style={{
          backgroundColor: terminalBackground,
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)'
        }}
      >
        <div ref={hostRef} className="hermes-chat-xterm-host min-h-0 min-w-0 flex-1" />
      </div>
    </div>
  )
}
