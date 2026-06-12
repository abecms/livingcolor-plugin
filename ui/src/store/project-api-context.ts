import { atom } from 'nanostores'

export const LOCAL_ORG_ID = 'local'

export const $apiOrgId = atom<string>(LOCAL_ORG_ID)
export const $apiProjectKey = atom<string | null>(null)

export function setProjectApiContext(orgId: string | null, projectKey: string | null): void {
  $apiOrgId.set((orgId ?? '').trim() || LOCAL_ORG_ID)
  const key = (projectKey ?? '').trim().toUpperCase()
  $apiProjectKey.set(key || null)
}
