import { atom } from 'nanostores'

export const $projectConfigRevision = atom(0)

export function bumpProjectConfigRevision(): void {
  $projectConfigRevision.set($projectConfigRevision.get() + 1)
}
