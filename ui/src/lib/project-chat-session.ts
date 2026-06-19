const STORAGE_KEY = 'livingcolor.projectChatSessions'
const STORAGE_SCHEMA_KEY = 'livingcolor.projectChatSessions.schema'
const STORAGE_SCHEMA_VERSION = 2

type ProjectChatSessionMap = Record<string, string>

function ensureStorageSchema(): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_SCHEMA_KEY)
    const version = raw ? Number.parseInt(raw, 10) : 0
    if (version >= STORAGE_SCHEMA_VERSION) {
      return
    }

    window.localStorage.removeItem(STORAGE_KEY)
    window.localStorage.setItem(STORAGE_SCHEMA_KEY, String(STORAGE_SCHEMA_VERSION))
  } catch {
    // ignore quota / privacy mode
  }
}

function loadMap(): ProjectChatSessionMap {
  if (typeof window === 'undefined') {
    return {}
  }

  ensureStorageSchema()

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)?.trim()
    if (!raw) {
      return {}
    }

    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object') {
      return {}
    }

    const map: ProjectChatSessionMap = {}
    for (const [projectKey, sessionId] of Object.entries(parsed)) {
      const key = projectKey.trim().toUpperCase()
      const id = String(sessionId || '').trim()
      if (key && id) {
        map[key] = id
      }
    }

    return map
  } catch {
    return {}
  }
}

function saveMap(map: ProjectChatSessionMap): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
    window.localStorage.setItem(STORAGE_SCHEMA_KEY, String(STORAGE_SCHEMA_VERSION))
  } catch {
    // ignore quota / privacy mode
  }
}

export function projectChatSessionTitle(projectKey: string): string {
  return `LivingColor ${projectKey.trim().toUpperCase()}`
}

export function isProjectChatSessionTitle(title: string | null | undefined, projectKey: string): boolean {
  return title?.trim() === projectChatSessionTitle(projectKey)
}

export function getProjectChatSessionId(projectKey: string): string | null {
  const key = projectKey.trim().toUpperCase()
  if (!key) {
    return null
  }

  return loadMap()[key] ?? null
}

export function setProjectChatSessionId(projectKey: string, sessionId: string): void {
  const key = projectKey.trim().toUpperCase()
  const id = sessionId.trim()

  if (!key || !id) {
    return
  }

  const map = loadMap()
  map[key] = id
  saveMap(map)
}

export function clearProjectChatSessionId(projectKey: string): void {
  const key = projectKey.trim().toUpperCase()
  if (!key) {
    return
  }

  const map = loadMap()
  if (!(key in map)) {
    return
  }

  delete map[key]
  saveMap(map)
}

export const PROJECT_CHAT_SESSION_ID_RE = /Session:\s*([A-Za-z0-9_-]{4,128})/

export async function ensureProjectChatSessionTitle(projectKey: string, sessionId: string): Promise<void> {
  const title = projectChatSessionTitle(projectKey)
  const id = sessionId.trim()
  if (!id) {
    return
  }

  const { getHermesPluginSdk } = await import('@/lib/hermes-plugin-sdk')
  const sdk = getHermesPluginSdk()
  try {
    await sdk?.api?.renameSession?.(id, title)
  } catch {
    // Best-effort — resume still works when the title is missing.
  }
}

export async function persistProjectChatSession(projectKey: string, sessionId: string): Promise<void> {
  const id = sessionId.trim()
  if (!id) {
    return
  }

  setProjectChatSessionId(projectKey, id)
  await ensureProjectChatSessionTitle(projectKey, id)
}

export function extractProjectChatSessionId(chunk: string): string | null {
  const plain = chunk.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '')
  const match = PROJECT_CHAT_SESSION_ID_RE.exec(plain)
  return match?.[1]?.trim() || null
}

export async function resolveProjectChatResumeSessionId(
  projectKey: string,
  storedSessionId: string | null
): Promise<string | null> {
  if (!storedSessionId?.trim()) {
    return null
  }

  const { fetchLivingColorProfileSessions, LIVINGCOLOR_PM_PROFILE } = await import('@/lib/hermes-plugin-sdk')
  const stored = storedSessionId.trim()

  try {
    const sessions = await fetchLivingColorProfileSessions(50)
    const match = sessions.find(
      session => session.id === stored && session.profile === LIVINGCOLOR_PM_PROFILE
    )

    if (match?.id) {
      if (!isProjectChatSessionTitle(match.title, projectKey)) {
        void ensureProjectChatSessionTitle(projectKey, match.id)
      }
      return match.id
    }

    clearProjectChatSessionId(projectKey)
    return null
  } catch {
    return stored
  }
}

export async function discoverProjectChatSessionId(projectKey: string): Promise<string | null> {
  const existing = getProjectChatSessionId(projectKey)
  if (existing) {
    return resolveProjectChatResumeSessionId(projectKey, existing)
  }

  const { fetchLivingColorProfileSessions, LIVINGCOLOR_PM_PROFILE } = await import('@/lib/hermes-plugin-sdk')

  try {
    const sessions = await fetchLivingColorProfileSessions(50)
    const titled = sessions.find(
      session =>
        session.profile === LIVINGCOLOR_PM_PROFILE &&
        isProjectChatSessionTitle(session.title, projectKey)
    )
    if (titled?.id) {
      await persistProjectChatSession(projectKey, titled.id)
      return titled.id
    }
  } catch {
    // Best-effort discovery only.
  }

  return null
}
