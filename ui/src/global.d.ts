interface LivingColorDesktopApi {
  openExternal?: (url: string) => Promise<void> | void
}

interface LivingColorDesktopBridge {
  api?: LivingColorDesktopApi
  openExternal?: (url: string) => Promise<void> | void
  firebaseGoogleSignIn?: () => Promise<{ ok: boolean; error?: string }>
  writeClipboard?: (text: string) => Promise<void> | void
  fetchLinkTitle?: (url: string) => Promise<string>
  touchBackend?: () => Promise<void> | void
}

declare module '*.png' {
  const src: string
  export default src
}

declare global {
  interface Window {
    livingColorDesktop?: LivingColorDesktopBridge
    __HERMES_PLUGIN_SDK__?: {
      sdkVersion?: string
      fetchJSON: (path: string, init?: RequestInit) => Promise<unknown>
      buildWsUrl?: (path: string, params?: Record<string, string>) => Promise<string>
      buildWsAuthParam?: () => Promise<[string, string]>
      api?: Record<string, (...args: never[]) => unknown>
      React?: typeof import('react')
    }
    __HERMES_PLUGINS__?: {
      register: (name: string, component: unknown) => void
      registerSlot?: (plugin: string, slot: string, component: unknown) => void
    }
  }
}

export {}
