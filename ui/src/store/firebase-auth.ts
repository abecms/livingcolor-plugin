import { atom } from 'nanostores'

export const $firebaseIdToken = atom<string | null>(null)
export const $firebaseActiveOrgId = atom<string | null>(null)

export function setFirebaseIdToken(token: string | null): void {
  $firebaseIdToken.set(token)
}

export function setFirebaseActiveOrgId(orgId: string | null): void {
  $firebaseActiveOrgId.set(orgId)
}
