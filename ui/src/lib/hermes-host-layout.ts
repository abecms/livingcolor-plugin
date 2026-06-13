/** Align the LivingColor plugin root with the Hermes main panel (below page header). */

export type HermesPluginShell = {
  panel: HTMLElement
  header: HTMLElement
}

export function findHermesPluginShell(root: HTMLElement): HermesPluginShell | null {
  let node: HTMLElement | null = root.parentElement
  while (node) {
    const header = node.querySelector(':scope > header[role="banner"]')
    if (header instanceof HTMLElement) {
      return { panel: node, header }
    }
    node = node.parentElement
  }
  return null
}

/** Pin `.lc-root` flush with the Hermes content column and page header. */
export function syncLcRootToHermesHost(root: HTMLElement): void {
  const shell = findHermesPluginShell(root)
  if (!shell) {
    const top = root.getBoundingClientRect().top
    const height = Math.max(0, window.innerHeight - top)
    root.style.position = ''
    root.style.top = ''
    root.style.left = ''
    root.style.width = ''
    root.style.zIndex = ''
    root.style.height = `${height}px`
    root.style.minHeight = `${height}px`
    return
  }

  const panelRect = shell.panel.getBoundingClientRect()
  const top = shell.header.getBoundingClientRect().bottom
  const height = Math.max(0, window.innerHeight - top)

  root.style.position = 'fixed'
  root.style.top = `${top}px`
  root.style.left = `${panelRect.left}px`
  root.style.width = `${panelRect.width}px`
  root.style.height = `${height}px`
  root.style.minHeight = `${height}px`
  root.style.margin = '0'
  root.style.zIndex = '2'
}
