/**
 * Entry point. Registers a thin wrapper (written against the HOST's React
 * via the plugin SDK) that mounts the full app into its own React root.
 * The wrapper is the only code that touches host React — the app runs in
 * the bundled React + ReactDOM so portals (Radix) and hooks are isolated.
 */
import { createRoot } from 'react-dom/client'
import { createElement } from 'react'
import App from './App'
import './styles.css'

const SDK = (window as any).__HERMES_PLUGIN_SDK__
const REGISTRY = (window as any).__HERMES_PLUGINS__

if (SDK && REGISTRY) {
  const HostReact = SDK.React
  function LivingColorTab() {
    const ref = HostReact.useRef(null)
    HostReact.useEffect(() => {
      if (!ref.current) return
      const root = createRoot(ref.current)
      root.render(createElement(App))
      return () => root.unmount()
    }, [])
    return HostReact.createElement('div', { ref, className: 'lc-root' })
  }
  REGISTRY.register('livingcolor', LivingColorTab)
}
