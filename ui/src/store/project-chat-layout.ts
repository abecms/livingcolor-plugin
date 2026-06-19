import { atom } from 'nanostores'

const CHAT_OPEN_STORAGE_KEY = 'livingcolor.projectChatOpen'
const CHAT_WIDTH_STORAGE_KEY = 'livingcolor.projectChatWidthPx'

const DEFAULT_WIDTH_PX = 352
const MIN_WIDTH_PX = 288
const MAX_WIDTH_PX = 512

function readStoredBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') {
    return fallback
  }

  try {
    const raw = window.localStorage.getItem(key)
    if (raw === 'true') {
      return true
    }
    if (raw === 'false') {
      return false
    }
  } catch {
    // ignore
  }

  return fallback
}

function writeStoredBoolean(key: string, value: boolean): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.localStorage.setItem(key, value ? 'true' : 'false')
  } catch {
    // ignore
  }
}

function readStoredWidth(): number {
  if (typeof window === 'undefined') {
    return DEFAULT_WIDTH_PX
  }

  try {
    const raw = Number(window.localStorage.getItem(CHAT_WIDTH_STORAGE_KEY))
    if (Number.isFinite(raw) && raw >= MIN_WIDTH_PX && raw <= MAX_WIDTH_PX) {
      return raw
    }
  } catch {
    // ignore
  }

  return DEFAULT_WIDTH_PX
}

function writeStoredWidth(value: number): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.localStorage.setItem(CHAT_WIDTH_STORAGE_KEY, String(value))
  } catch {
    // ignore
  }
}

export const PROJECT_CHAT_MIN_WIDTH_PX = MIN_WIDTH_PX
export const PROJECT_CHAT_MAX_WIDTH_PX = MAX_WIDTH_PX

export const PROJECT_CHAT_OPEN_CHANGED_EVENT = 'livingcolor:project-chat-open-changed'

export const $projectChatOpen = atom(readStoredBoolean(CHAT_OPEN_STORAGE_KEY, true))
export const $projectChatWidthPx = atom(readStoredWidth())

if (typeof window !== 'undefined') {
  window.addEventListener(PROJECT_CHAT_OPEN_CHANGED_EVENT, event => {
    const detail = (event as CustomEvent<{ open?: boolean }>).detail
    if (typeof detail?.open === 'boolean' && detail.open !== $projectChatOpen.get()) {
      $projectChatOpen.set(detail.open)
    }
  })
}

$projectChatOpen.subscribe(open => writeStoredBoolean(CHAT_OPEN_STORAGE_KEY, open))
$projectChatWidthPx.subscribe(width => writeStoredWidth(width))

export function toggleProjectChatOpen(): void {
  setProjectChatOpen(!$projectChatOpen.get())
}

export function setProjectChatOpen(open: boolean): void {
  $projectChatOpen.set(open)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(PROJECT_CHAT_OPEN_CHANGED_EVENT, { detail: { open } }))
  }
}

export function setProjectChatWidthPx(width: number): void {
  const bounded = Math.min(MAX_WIDTH_PX, Math.max(MIN_WIDTH_PX, Math.round(width)))
  $projectChatWidthPx.set(bounded)
}
