/** Local-mode stub — org/cloud Firebase APIs are unavailable in the plugin tab. */

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

export interface FirebaseOrgInvite {
  id: string
  email: string
  role: string
  status: string
  invitedAt?: string
  invitedBy?: string
}

export interface FirebaseClientConfigResponse {
  enabled: boolean
  config: Record<string, string> | null
}

export async function ensureFirebaseSession(): Promise<null> {
  return null
}

export function bootstrapFirebaseSession(): Promise<FirebaseBootstrapResponse> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function fetchFirebaseMe(): Promise<FirebaseBootstrapResponse> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function fetchFirebasePreferences(): Promise<FirebasePreferencesResponse> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function saveFirebasePreferences(
  _selectedJiraProjectKey: string | null
): Promise<FirebasePreferencesResponse> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function createFirebaseTeamOrg(_name: string): Promise<FirebaseOrgSummary> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function setFirebaseActiveOrg(_orgId: string): Promise<{
  activeOrgId: string
  organizations: FirebaseOrgSummary[]
}> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function fetchOrgMembers(_orgId: string): Promise<{ orgId: string; members: FirebaseOrgMember[] }> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function inviteOrgMember(
  _orgId: string,
  _email: string,
  _role: 'admin' | 'member' = 'member'
): Promise<{ orgId: string; status: 'added' | 'invited'; member?: FirebaseOrgMember; invite?: Record<string, string> }> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function removeOrgMember(_orgId: string, _memberUid: string): Promise<{ orgId: string; removedUid: string }> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function fetchOrgInvites(_orgId: string): Promise<{ orgId: string; invites: FirebaseOrgInvite[] }> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function revokeOrgInvite(_orgId: string, _inviteId: string): Promise<{ orgId: string; revokedInviteId: string }> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function fetchOrgProjects(_orgId: string): Promise<{ orgId: string; projects: FirebaseOrgProject[] }> {
  return Promise.resolve({ orgId: _orgId, projects: [] })
}

export function saveOrgProjectConfig(
  _orgId: string,
  _jiraProjectKey: string,
  _payload: { projectName?: string; mapping?: Record<string, unknown>; deliverySettings?: Record<string, unknown> }
): Promise<Record<string, unknown>> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function shareLocalProjectToOrg(
  _orgId: string,
  _jiraProjectKey: string
): Promise<{ orgId: string; project: FirebaseOrgProject & Record<string, unknown> }> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function createOrgProject(
  _orgId: string,
  jiraProjectKey: string,
  projectName: string
): Promise<{ orgId: string; project: FirebaseOrgProject }> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function deleteOrgProject(
  _orgId: string,
  _jiraProjectKey: string
): Promise<{ orgId: string; deletedProjectKey: string }> {
  return Promise.reject(new Error('Firebase is not available in the LivingColor plugin'))
}

export function fetchFirebaseClientConfig(): Promise<FirebaseClientConfigResponse> {
  return Promise.resolve({ enabled: false, config: null })
}
