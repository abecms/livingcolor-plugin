/**
 * Entry point. Registers a thin wrapper (written against the HOST's React
 * via the plugin SDK) that mounts the full app into its own React root.
 * The wrapper is the only code that touches host React — the app runs in
 * the bundled React + ReactDOM so portals (Radix) and hooks are isolated.
 */
import { createRoot } from 'react-dom/client'
import { createElement } from 'react'
import App from './App'
import { installHermesNavBrand } from '@/lib/hermes-nav-brand'
import { findHermesPluginShell, syncLcRootToHermesHost } from '@/lib/hermes-host-layout'
import './styles.css'

const SDK = (window as any).__HERMES_PLUGIN_SDK__
const REGISTRY = (window as any).__HERMES_PLUGINS__

if (!SDK || !REGISTRY) {
  console.error(
    '[livingcolor] Hermes plugin SDK missing — register() was not called. ' +
      'Ensure the dashboard host loaded before this script.',
  )
}

if (SDK && REGISTRY) {
  const HostReact = SDK.React

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
  REGISTRY.register('livingcolor', LivingColorTab)
  installHermesNavBrand()
}
