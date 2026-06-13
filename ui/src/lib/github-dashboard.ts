export interface GitHubConnectResponse {
  ok: boolean
  status: 'connected' | 'disconnected' | 'connecting' | 'error'
  message: string
  authenticated: boolean
  toolCount: number
  saved?: boolean
}

export interface GitHubConnectionStatus {
  ok: boolean
  status: 'connected' | 'disconnected' | 'connecting' | 'error'
  message: string
  authenticated: boolean
  toolCount: number
}
