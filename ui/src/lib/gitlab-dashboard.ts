export interface GitLabConnectResponse {
  ok: boolean
  status: 'connected' | 'disconnected' | 'connecting' | 'error'
  message: string
  authenticated: boolean
  toolCount: number
  gitlabUrl?: string | null
  saved?: boolean
}

export interface GitLabConnectionStatus {
  ok: boolean
  status: 'connected' | 'disconnected' | 'connecting' | 'error'
  message: string
  authenticated: boolean
  toolCount: number
  gitlabUrl?: string | null
}
