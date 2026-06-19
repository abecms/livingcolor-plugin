import { useEffect, useState } from 'react'

/** Matches Hermes dashboard ChatPage static xterm colors (foreground/cursor). */
export const HERMES_TERMINAL_THEME_STATIC = {
  foreground: '#f0e6d2',
  cursor: '#f0e6d2',
  cursorAccent: '#0d2626',
  selectionBackground: '#f0e6d244'
} as const

const TERMINAL_BACKGROUND_VAR = '--theme-terminal-background'
const TERMINAL_BACKGROUND_FALLBACK = '#000000'

export function readHermesTerminalBackground(): string {
  if (typeof document === 'undefined') {
    return TERMINAL_BACKGROUND_FALLBACK
  }

  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(TERMINAL_BACKGROUND_VAR)
    .trim()

  return value || TERMINAL_BACKGROUND_FALLBACK
}

export function useHermesTerminalBackground(): string {
  const [background, setBackground] = useState(readHermesTerminalBackground)

  useEffect(() => {
    const sync = () => {
      setBackground(readHermesTerminalBackground())
    }

    sync()

    const observer = new MutationObserver(sync)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['style', 'class']
    })

    return () => {
      observer.disconnect()
    }
  }, [])

  return background
}
