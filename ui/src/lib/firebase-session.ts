import { callCloudApi } from '@/lib/cloud-api'
import { callDesktopApi } from '@/lib/desktop-api'

export interface FirebaseOrgSummary {
  id: string
  name: string
  kind: 'personal' | 'team' | string
  role: string
}

export interface FirebaseUserSummary {
  uid: string
  email: string
  displayName: string
  activeOrgId: string
}

export interface FirebaseBootstrapResponse {
  user: FirebaseUserSummary
  organizations: FirebaseOrgSummary[]
}

export interface FirebasePreferencesResponse {
  orgId: string
  preferences: {
    selectedJiraProjectKey?: string | null
    updatedAt?: string
    createdAt?: string
  }
}

export interface FirebaseOrgMember {
  uid: string
  email: string
  displayName: string
  role: string
  joinedAt?: string
}

export interface FirebaseOrgProject {
  jiraProjectKey: string
  projectName?: string
  updatedAt?: string
}

export function bootstrapFirebaseSession(): Promise<FirebaseBootstrapResponse> {
  return callCloudApi({ path: '/v1/session/bootstrap', method: 'POST' })
}

export function fetchFirebaseMe(): Promise<FirebaseBootstrapResponse> {
  return callCloudApi({ path: '/v1/me' })
}

export function fetchFirebasePreferences(): Promise<FirebasePreferencesResponse> {
  return callCloudApi({ path: '/v1/preferences' })
}

export function saveFirebasePreferences(
  selectedJiraProjectKey: string | null
): Promise<FirebasePreferencesResponse> {
  return callCloudApi({
    path: '/v1/preferences',
    method: 'PUT',
    body: { selectedJiraProjectKey }
  })
}

export function createFirebaseTeamOrg(name: string): Promise<FirebaseOrgSummary> {
  return callCloudApi({ path: '/v1/orgs', method: 'POST', body: { name } })
}

export function setFirebaseActiveOrg(orgId: string): Promise<{
  activeOrgId: string
  organizations: FirebaseOrgSummary[]
}> {
  return callCloudApi({ path: '/v1/me/active-org', method: 'PUT', body: { orgId } })
}

export function fetchOrgMembers(orgId: string): Promise<{ orgId: string; members: FirebaseOrgMember[] }> {
  return callCloudApi({ path: `/v1/orgs/${encodeURIComponent(orgId)}/members` })
}

export function inviteOrgMember(
  orgId: string,
  email: string,
  role: 'admin' | 'member' = 'member'
): Promise<{ orgId: string; status: 'added' | 'invited'; member?: FirebaseOrgMember; invite?: Record<string, string> }> {
  return callCloudApi({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/members`,
    method: 'POST',
    body: { email, role }
  })
}

export function removeOrgMember(orgId: string, memberUid: string): Promise<{ orgId: string; removedUid: string }> {
  return callCloudApi({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(memberUid)}`,
    method: 'DELETE'
  })
}

export interface FirebaseOrgInvite {
  id: string
  email: string
  role: string
  status: string
  invitedAt?: string
  invitedBy?: string
}

export function fetchOrgInvites(orgId: string): Promise<{ orgId: string; invites: FirebaseOrgInvite[] }> {
  return callCloudApi({ path: `/v1/orgs/${encodeURIComponent(orgId)}/invites` })
}

export function revokeOrgInvite(orgId: string, inviteId: string): Promise<{ orgId: string; revokedInviteId: string }> {
  return callCloudApi({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/invites/${encodeURIComponent(inviteId)}`,
    method: 'DELETE'
  })
}

export function fetchOrgProjects(orgId: string): Promise<{ orgId: string; projects: FirebaseOrgProject[] }> {
  return callCloudApi({ path: `/v1/orgs/${encodeURIComponent(orgId)}/projects` })
}

export function saveOrgProjectConfig(
  orgId: string,
  jiraProjectKey: string,
  payload: { projectName?: string; mapping?: Record<string, unknown>; deliverySettings?: Record<string, unknown> }
): Promise<Record<string, unknown>> {
  return callCloudApi({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/projects/${encodeURIComponent(jiraProjectKey)}`,
    method: 'PUT',
    body: payload
  })
}

export async function shareLocalProjectToOrg(
  orgId: string,
  jiraProjectKey: string
): Promise<{ orgId: string; project: FirebaseOrgProject & Record<string, unknown> }> {
  const key = jiraProjectKey.trim().toUpperCase()
  const payload = await callDesktopApi<{
    jiraProjectKey: string
    projectName: string
    mapping?: Record<string, unknown> | null
    deliverySettings?: Record<string, unknown>
  }>({
    path: `/api/delivery/projects/${encodeURIComponent(key)}/share-payload`
  })
  const shared = await callCloudApi<{ orgId: string; project: FirebaseOrgProject & Record<string, unknown> }>({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/projects/share-local`,
    method: 'POST',
    body: payload
  })
  await callDesktopApi({
    path: `/api/delivery/projects/${encodeURIComponent(key)}/finalize-share`,
    method: 'POST'
  })
  return shared
}

export function createOrgProject(
  orgId: string,
  jiraProjectKey: string,
  projectName: string
): Promise<{ orgId: string; project: FirebaseOrgProject }> {
  return callCloudApi({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/projects`,
    method: 'POST',
    body: { jiraProjectKey, projectName }
  })
}

export function deleteOrgProject(
  orgId: string,
  jiraProjectKey: string
): Promise<{ orgId: string; deletedProjectKey: string }> {
  return callCloudApi({
    path: `/v1/orgs/${encodeURIComponent(orgId)}/projects/${encodeURIComponent(jiraProjectKey)}`,
    method: 'DELETE'
  })
}

export interface FirebaseClientConfigResponse {
  enabled: boolean
  config: Record<string, string> | null
}

export async function fetchFirebaseClientConfig(): Promise<FirebaseClientConfigResponse> {
  try {
    return await callDesktopApi<FirebaseClientConfigResponse>({
      path: '/api/firebase/client-config'
    })
  } catch {
    return callCloudApi({ path: '/v1/config/firebase-client', public: true })
  }
}
