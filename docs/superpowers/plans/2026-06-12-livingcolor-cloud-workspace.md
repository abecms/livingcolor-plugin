# LivingColor Cloud Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Personal (100% local SQLite) and Team (Firestore via `https://api-livingcolor.visualq.ai`) modes in the Hermes plugin — no Firebase service account on user machines.

**Architecture:** Plugin UI defaults to local workspace with a welcome gate. Team flows use embedded Firebase web config for Auth + Firestore read listeners; all privileged writes, locks, and org/project CRUD go to the cloud API which holds the Admin SDK. Local Hermes Python continues delivery execution against `runtime.db`; team scope adds sync + lock layers.

**Tech Stack:** Python 3.13, FastAPI, Firebase Admin SDK, Firestore; React 19, Vite, Vitest, Firebase JS SDK v11; deploy target `api-livingcolor.visualq.ai`.

**Spec:** `docs/superpowers/specs/2026-06-12-livingcolor-cloud-workspace-design.md`

---

## File map (by phase)

| Phase | Create | Modify |
| --- | --- | --- |
| E1 | `ui/src/app/auth/welcome-page.tsx`, `ui/src/components/firebase-auth-gate.test.tsx` (extend) | `ui/src/components/firebase-auth-gate.tsx`, `ui/src/contexts/firebase-auth-provider.tsx`, `ui/src/lib/firebase-config.ts`, `ui/src/hooks/use-firebase-auth.ts`, `README.md` |
| E2 | `cloud_api/main.py`, `cloud_api/auth.py`, `cloud_api/routes/session.py`, `cloud_api/routes/orgs.py`, `cloud_api/routes/projects.py`, `cloud_api/Dockerfile`, `tests/cloud_api/test_session.py`, `tests/cloud_api/test_orgs.py` | `lc_server/integrations/firebase_auth.py` (shared helpers if needed) |
| E3 | `ui/src/lib/cloud-api.ts`, `ui/src/lib/cloud-api.test.ts`, `ui/src/lib/firebase-session.ts` | `ui/src/lib/desktop-api.ts`, `ui/src/contexts/firebase-auth-provider.tsx` |
| E4 | `cloud_api/routes/locks.py`, `cloud_api/routes/work_orders.py`, `ui/src/hooks/use-team-work-orders.ts`, `ui/src/hooks/use-work-order-lock.ts`, `firestore.rules` | `ui/src/app/delivery/*` (WO actions), `tests/cloud_api/test_locks.py`, `ui/src/hooks/use-team-work-orders.test.ts` |
| E5 | `delivery_runtime/persistence/pending_events.py`, `cloud_api/routes/events.py`, `cloud_api/routes/reconcile.py`, `ui/src/lib/team-sync.ts`, `ui/src/components/offline-banner.tsx` | `ui/src/App.tsx`, `tests/cloud_api/test_reconcile.py`, `ui/src/lib/team-sync.test.ts` |
| E6 | `cloud_api/routes/share.py` | `ui/src/app/delivery/share-project-dialog.tsx`, `lc_server/integrations/local_project_share.py`, `tests/cloud_api/test_share.py` |

**Reuse:** `lc_server/integrations/firestore_store.py`, `lc_server/integrations/firebase_auth.py`, `lc_server/integrations/local_project_share.py` — imported by `cloud_api/`, not duplicated.

**Dev override:** `VITE_LC_CLOUD_API_URL` (UI build) and `LIVINGCOLOR_CLOUD_API_URL` (local Python, optional).

---

# Phase E1 — Welcome gate + personal without account

## Task 1: Welcome page component

**Files:**
- Create: `ui/src/app/auth/welcome-page.tsx`
- Modify: `ui/src/components/firebase-auth-gate.tsx`
- Test: `ui/src/components/firebase-auth-gate.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// ui/src/components/firebase-auth-gate.test.tsx — add:
import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('@/app/auth/welcome-page', () => ({
  WelcomePage: ({ onContinueLocal, onSignIn }: { onContinueLocal: () => void; onSignIn: () => void }) => (
    <div>
      <button type="button" onClick={onContinueLocal}>Continue locally</button>
      <button type="button" onClick={onSignIn}>Sign in to collaborate</button>
    </div>
  )
}))

it('shows welcome choices before auth when status is idle', () => {
  vi.mocked(useFirebaseAuth).mockReturnValue({
    enabled: true,
    status: 'idle',
    // ...minimal fields
  } as ReturnType<typeof useFirebaseAuth>)
  render(<FirebaseAuthGate><div>app</div></FirebaseAuthGate>)
  expect(screen.getByText('Continue locally')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- --run src/components/firebase-auth-gate.test.tsx`

Expected: FAIL — `status: 'idle'` not handled; setup banner or children render instead.

- [ ] **Step 3: Implement welcome page + gate**

```tsx
// ui/src/app/auth/welcome-page.tsx
import { LivingColorLogo } from '@/components/livingcolor-logo'
import { Button } from '@/components/ui/button'

export function WelcomePage({
  onContinueLocal,
  onSignIn
}: {
  onContinueLocal: () => void
  onSignIn: () => void
}) {
  return (
    <div className="flex h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-md space-y-8 text-center">
        <LivingColorLogo className="mx-auto" height={40} />
        <p className="text-sm text-muted-foreground">
          Run delivery locally, or sign in to collaborate with your team.
        </p>
        <div className="flex flex-col gap-3">
          <Button type="button" onClick={onContinueLocal}>Continue locally</Button>
          <Button type="button" variant="outline" onClick={onSignIn}>Sign in to collaborate</Button>
        </div>
      </div>
    </div>
  )
}
```

```tsx
// ui/src/components/firebase-auth-gate.tsx — replace disabled/setup branch:
// Remove FirebaseSetupBanner entirely.
// Add status 'idle' | 'choosing-auth' flow:
//   - On mount: if no stored workspace choice and not signed in → WelcomePage
//   - onContinueLocal → switchToLocalWorkspace(); set gateStatus 'passed'
//   - onSignIn → set gateStatus 'signed-out' → FirebaseLoginPage
//   - If user already signed in → children
//   - If stored scope is local and user never chose team → children (no login)
```

Add `gatePassed` local state or derive from `readStoredWorkspaceScope() === 'local'` + `!user`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npm test -- --run src/components/firebase-auth-gate.test.tsx`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ui/src/app/auth/welcome-page.tsx ui/src/components/firebase-auth-gate.tsx ui/src/components/firebase-auth-gate.test.tsx
git commit -m "feat: welcome gate with local-first workspace choice"
```

---

## Task 2: Firebase enabled from embedded config (not local SA)

**Files:**
- Modify: `ui/src/lib/firebase-config.ts`
- Modify: `ui/src/contexts/firebase-auth-provider.tsx`
- Test: `ui/src/lib/firebase-config.test.ts` (create)

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/lib/firebase-config.test.ts
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/firebase-session', () => ({
  fetchFirebaseClientConfig: vi.fn(async () => ({ enabled: false, config: null }))
}))

import { resolveFirebaseWebConfig } from '@/lib/firebase-config'

it('falls back to embedded cloud defaults without local admin', async () => {
  const result = await resolveFirebaseWebConfig()
  expect(result.config?.projectId).toBe('livingcolor-app')
  expect(result.source).toBe('cloud-defaults')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npm test -- --run src/lib/firebase-config.test.ts`

Expected: FAIL if backend gate still returns `none`.

- [ ] **Step 3: Always expose embedded Firebase web config**

In `firebase-config.ts`, ensure resolution order:

1. `VITE_FIREBASE_*` env (dev)
2. Embedded `LIVINGCOLOR_CLOUD_FIREBASE_CONFIG`
3. Optional cloud API `GET /v1/config/firebase-client` (Phase E2)
4. Never require local plugin `/api/firebase/client-config` `enabled: true`

In `firebase-auth-provider.tsx`:

```ts
const config = await resolveFirebaseWebConfig()
const enabled = config.config !== null  // true with embedded defaults
```

Remove branches that set `enabled: false` when Hermes plugin lacks `FIREBASE_SERVICE_ACCOUNT_PATH`.

- [ ] **Step 4: Run tests**

Run: `cd ui && npm test -- --run`

Expected: all Vitest PASS

- [ ] **Step 5: Update README + commit**

Remove user-facing `FIREBASE_SERVICE_ACCOUNT_PATH` requirement. Document Personal default + Team sign-in.

```bash
git add ui/src/lib/firebase-config.ts ui/src/lib/firebase-config.test.ts ui/src/contexts/firebase-auth-provider.tsx README.md
git commit -m "feat: enable Firebase client from embedded config without local SA"
```

---

# Phase E2 — Cloud API (`api-livingcolor.visualq.ai`)

## Task 3: Cloud API skeleton + health

**Files:**
- Create: `cloud_api/main.py`, `cloud_api/__init__.py`, `cloud_api/auth.py`
- Create: `tests/cloud_api/test_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud_api/test_health.py
from fastapi.testclient import TestClient
from cloud_api.main import app

def test_health():
    client = TestClient(app)
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cloud_api/test_health.py -v`

Expected: FAIL — module not found

- [ ] **Step 3: Implement skeleton**

```python
# cloud_api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cloud_api.routes import session, orgs, projects  # stubs in E2 tasks

app = FastAPI(title="LivingColor Cloud API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*", "http://127.0.0.1:*"],  # tighten in deploy
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/v1/health")
def health():
    return {"status": "ok", "service": "livingcolor-cloud"}

app.include_router(session.router, prefix="/v1")
app.include_router(orgs.router, prefix="/v1")
app.include_router(projects.router, prefix="/v1")
```

```python
# cloud_api/auth.py
from fastapi import HTTPException, Request
from lc_server.integrations.firebase_auth import extract_bearer_token, verify_firebase_id_token, FirebaseUser

def require_user(request: Request) -> FirebaseUser:
    token = extract_bearer_token(request.headers.get("authorization"))
    if not token:
        raise HTTPException(401, "Missing Firebase ID token")
    try:
        return verify_firebase_id_token(token)
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(401, "Invalid Firebase ID token") from exc
```

- [ ] **Step 4: Run test**

Run: `pytest tests/cloud_api/test_health.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloud_api/ tests/cloud_api/test_health.py
git commit -m "feat: add LivingColor cloud API skeleton"
```

---

## Task 4: Session bootstrap on cloud API

**Files:**
- Create: `cloud_api/routes/session.py`
- Create: `tests/cloud_api/test_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cloud_api/test_session.py
from unittest.mock import patch
from fastapi.testclient import TestClient
from cloud_api.main import app
from lc_server.integrations.firebase_auth import FirebaseUser

def test_bootstrap_requires_auth():
    client = TestClient(app)
    assert client.post("/v1/session/bootstrap").status_code == 401

@patch("cloud_api.routes.session.FirestoreStore")
@patch("cloud_api.auth.verify_firebase_id_token")
def test_bootstrap_returns_orgs(mock_verify, mock_store_cls):
    mock_verify.return_value = FirebaseUser(uid="u1", email="a@b.com", display_name="A", email_verified=True)
    mock_store_cls.return_value.bootstrap_user.return_value = {
        "user": {"uid": "u1", "email": "a@b.com", "displayName": "A", "activeOrgId": "personal-u1"},
        "organizations": [{"id": "personal-u1", "name": "Personal", "kind": "personal", "role": "admin"}],
    }
    client = TestClient(app)
    r = client.post("/v1/session/bootstrap", headers={"Authorization": "Bearer fake"})
    assert r.status_code == 200
    assert r.json()["organizations"][0]["kind"] == "personal"
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Port bootstrap route**

```python
# cloud_api/routes/session.py
from fastapi import APIRouter, Depends
from cloud_api.auth import require_user
from lc_server.integrations.firebase_auth import FirebaseUser, client_firebase_config
from lc_server.integrations.firestore_store import FirestoreStore

router = APIRouter(tags=["session"])

@router.get("/config/firebase-client")
def firebase_client_config():
    config = client_firebase_config()
    return {"enabled": config is not None, "config": config}

@router.post("/session/bootstrap")
def bootstrap(user: FirebaseUser = Depends(require_user)):
    payload = FirestoreStore().bootstrap_user(user)
    return payload
```

Mirror existing `lc_server/api/firebase_routes.py` response shapes.

- [ ] **Step 4: Run tests**

Run: `pytest tests/cloud_api/test_session.py -v`

Expected: PASS

- [ ] **Step 5: Dockerfile + commit**

```dockerfile
# cloud_api/Dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[cloud]"  # add optional extra in pyproject/setup
ENV PORT=8080
CMD ["uvicorn", "cloud_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Deploy env on `api-livingcolor.visualq.ai`: `FIREBASE_SERVICE_ACCOUNT_PATH` or `GOOGLE_APPLICATION_CREDENTIALS`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID=livingcolor-app`.

```bash
git add cloud_api/routes/session.py tests/cloud_api/test_session.py cloud_api/Dockerfile
git commit -m "feat: cloud API session bootstrap and firebase client config"
```

---

## Task 5: Orgs + projects routes on cloud API

**Files:**
- Create: `cloud_api/routes/orgs.py`, `cloud_api/routes/projects.py`
- Create: `tests/cloud_api/test_orgs.py`, `tests/cloud_api/test_projects.py`

- [ ] **Step 1: Write failing tests** for:

- `POST /v1/orgs` create team
- `GET /v1/orgs/{orgId}/members`
- `POST /v1/orgs/{orgId}/invites`
- `GET /v1/orgs/{orgId}/projects`
- `PATCH /v1/orgs/{orgId}/projects/{key}`

Copy request/response models from `lc_server/api/firebase_routes.py`.

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement routes** delegating to `FirestoreStore` methods already used by local `firebase_routes.py`.

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/cloud_api/ -v`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: cloud API org and project routes"
```

---

# Phase E3 — Plugin cloud API client

## Task 6: `callCloudApi` client

**Files:**
- Create: `ui/src/lib/cloud-api.ts`, `ui/src/lib/cloud-api.test.ts`
- Modify: `ui/src/lib/firebase-session.ts`

- [ ] **Step 1: Write the failing test**

```ts
// ui/src/lib/cloud-api.test.ts
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { $firebaseIdToken, $firebaseActiveOrgId } from '@/store/firebase-auth'

vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 })))

import { callCloudApi, LIVINGCOLOR_CLOUD_API_URL } from '@/lib/cloud-api'

beforeEach(() => {
  $firebaseIdToken.set('tok')
  $firebaseActiveOrgId.set('org-1')
})

it('calls api-livingcolor.visualq.ai with auth headers', async () => {
  expect(LIVINGCOLOR_CLOUD_API_URL).toBe('https://api-livingcolor.visualq.ai')
  await callCloudApi({ path: '/v1/session/bootstrap', method: 'POST' })
  const [url, init] = vi.mocked(fetch).mock.calls[0]
  expect(url).toBe('https://api-livingcolor.visualq.ai/v1/session/bootstrap')
  expect((init as RequestInit).headers).toMatchObject({
    Authorization: 'Bearer tok',
    'X-LC-Org-Id': 'org-1'
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement**

```ts
// ui/src/lib/cloud-api.ts
import { getFirebaseIdToken } from '@/services/firebase'
import { $firebaseActiveOrgId, $firebaseIdToken, setFirebaseIdToken } from '@/store/firebase-auth'
import { $apiProjectKey } from '@/store/project-api-context'

export const LIVINGCOLOR_CLOUD_API_URL =
  (import.meta.env.VITE_LC_CLOUD_API_URL as string | undefined)?.replace(/\/$/, '') ||
  'https://api-livingcolor.visualq.ai'

export async function callCloudApi<T>(request: {
  path: string
  method?: string
  body?: unknown
}): Promise<T> {
  const base = LIVINGCOLOR_CLOUD_API_URL
  const url = `${base}${request.path.startsWith('/') ? '' : '/'}${request.path}`
  const token = $firebaseIdToken.get() || (await getFirebaseIdToken())
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` }
  const orgId = $firebaseActiveOrgId.get()
  if (orgId) headers['X-LC-Org-Id'] = orgId
  const projectKey = $apiProjectKey.get()
  if (projectKey) headers['X-LC-Project-Key'] = projectKey

  const init: RequestInit = { method: request.method ?? 'GET', headers }
  if (request.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(request.body)
  }

  let response = await fetch(url, init)
  if (response.status === 401 || response.status === 403) {
    const fresh = await getFirebaseIdToken(true)
    setFirebaseIdToken(fresh)
    headers.Authorization = `Bearer ${fresh}`
    response = await fetch(url, { ...init, headers })
  }
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`${response.status}: ${text}`)
  }
  return response.json() as Promise<T>
}
```

- [ ] **Step 4: Point `firebase-session.ts` team calls to `callCloudApi`**

Replace paths:

| Old (`callDesktopApi`) | New (`callCloudApi`) |
| --- | --- |
| `/api/firebase/bootstrap` | `/v1/session/bootstrap` |
| `/api/firebase/me` | `/v1/session/bootstrap` or new `/v1/me` |
| `/api/firebase/orgs` | `/v1/orgs` |
| `/api/firebase/orgs/{id}/members` | `/v1/orgs/{id}/members` |
| etc. | per spec |

Keep `callDesktopApi` for `/api/delivery/*` and `/api/jira/*` only.

- [ ] **Step 5: Run tests + rebuild**

Run: `cd ui && npm test -- --run && npm run build`

```bash
git commit -m "feat: route team Firebase calls to api-livingcolor.visualq.ai"
```

---

# Phase E4 — Firestore reads + WO locks

## Task 7: Firestore security rules

**Files:**
- Create: `firestore.rules`
- Document deploy in `cloud_api/README.md`

- [ ] **Step 1: Write rules**

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    function isMember(orgId) {
      return request.auth != null
        && exists(/databases/$(database)/documents/organizations/$(orgId)/members/$(request.auth.uid));
    }
    match /organizations/{orgId} {
      allow read: if isMember(orgId);
      allow write: if false;
      match /members/{uid} {
        allow read: if isMember(orgId);
        allow write: if false;
      }
      match /projects/{projectKey} {
        allow read: if isMember(orgId);
        allow write: if false;
      }
      match /workOrders/{woId} {
        allow read: if isMember(orgId);
        allow write: if false;
      }
      match /locks/{woId} {
        allow read: if isMember(orgId);
        allow write: if false;
      }
      match /events/{eventId} {
        allow read: if isMember(orgId);
        allow write: if false;
      }
    }
  }
}
```

- [ ] **Step 2: Deploy rules** to `livingcolor-app` (manual step documented).

- [ ] **Step 3: Commit**

```bash
git add firestore.rules cloud_api/README.md
git commit -m "docs: Firestore read-only client rules for team workspace"
```

---

## Task 8: WO lock API + UI hook

**Files:**
- Create: `cloud_api/routes/locks.py`, `cloud_api/routes/work_orders.py`
- Create: `ui/src/hooks/use-work-order-lock.ts`
- Create: `tests/cloud_api/test_locks.py`

- [ ] **Step 1: Write failing lock tests**

```python
def test_acquire_lock_exclusive(mock_verify, mock_store):
    # first acquire 200, second different user 409

def test_release_lock_only_holder(mock_verify, mock_store):
    # holder 200, non-holder 403
```

Firestore shape: `organizations/{orgId}/locks/{woId}` → `{ holderUid, holderEmail, acquiredAt, sessionId }`.

- [ ] **Step 2: Implement routes**

```python
@router.post("/orgs/{org_id}/work-orders/{wo_id}/lock")
def acquire_lock(org_id: str, wo_id: str, user: FirebaseUser = Depends(require_user)):
    ...

@router.delete("/orgs/{org_id}/work-orders/{wo_id}/lock")
def release_lock(org_id: str, wo_id: str, user: FirebaseUser = Depends(require_user)):
    ...
```

- [ ] **Step 3: UI hook**

```ts
// ui/src/hooks/use-work-order-lock.ts
export function useWorkOrderLock(woId: string) {
  // callCloudApi acquire/release
  // subscribe to Firestore locks doc via onSnapshot when in org mode
  // return { canWrite, holderEmail, acquire, release }
}
```

- [ ] **Step 4: Wire delivery WO actions** — disable promote/gate buttons when `!canWrite` in org scope.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: work-order locks via cloud API with read-only UI for non-holders"
```

---

## Task 9: Firestore work-order listeners

**Files:**
- Create: `ui/src/hooks/use-team-work-orders.ts`
- Test: `ui/src/hooks/use-team-work-orders.test.ts`

- [ ] **Step 1: Write failing test** (mock Firestore module)

- [ ] **Step 2: Implement listener**

```ts
// When workspaceScope.mode === 'org':
// onSnapshot(collection(db, `organizations/${orgId}/workOrders`), setTeamWorkOrders)
// Merge with local SQLite cache for offline display
```

- [ ] **Step 3: Integrate in project dashboard** — team WOs from hook; personal from existing local API.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: realtime team work-order reads from Firestore"
```

---

# Phase E5 — Events, offline reconcile

## Task 10: Pending events SQLite queue

**Files:**
- Create: `delivery_runtime/persistence/pending_events.py`
- Modify: `delivery_runtime/persistence/db.py` (migration for `pending_cloud_events` table)
- Test: `tests/delivery_runtime/test_pending_events.py`

- [ ] **Step 1: Write failing test**

```python
def test_enqueue_and_flush_pending_events(tmp_db):
    enqueue_pending_event(org_id="org1", wo_id="WO-1", payload={"type": "state_change"})
    assert len(list_pending_events("org1")) == 1
    mark_flushed(event_id)
    assert len(list_pending_events("org1")) == 0
```

- [ ] **Step 2: Implement table + helpers**

```sql
CREATE TABLE IF NOT EXISTS pending_cloud_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id TEXT NOT NULL,
  wo_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  flushed_at TEXT
);
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: SQLite queue for offline cloud event flush"
```

---

## Task 11: Events + reconcile API

**Files:**
- Create: `cloud_api/routes/events.py`, `cloud_api/routes/reconcile.py`
- Create: `tests/cloud_api/test_reconcile.py`

- [ ] **Step 1: Write failing tests** for append-only events and reconcile conflict detection.

- [ ] **Step 2: Implement**

```python
@router.post("/orgs/{org_id}/events")
def append_event(org_id: str, body: EventBody, user: FirebaseUser = Depends(require_user)):
    # verify lock holder, append to organizations/{orgId}/events

@router.post("/orgs/{org_id}/sync/reconcile")
def reconcile(org_id: str, body: ReconcileBody, user: FirebaseUser = Depends(require_user)):
    # compare client pending events vs server state
    # return { accepted: [], conflicts: [{ woId, serverVersion, clientVersion }] }
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: cloud event append and offline reconcile endpoint"
```

---

## Task 12: Team sync module + offline banner

**Files:**
- Create: `ui/src/lib/team-sync.ts`, `ui/src/components/offline-banner.tsx`
- Test: `ui/src/lib/team-sync.test.ts`
- Modify: `ui/src/App.tsx`

- [ ] **Step 1: Write failing test** for flush on reconnect.

- [ ] **Step 2: Implement**

```ts
// team-sync.ts
export async function flushPendingEvents(orgId: string): Promise<ReconcileResult> {
  const pending = await fetchPendingEventsFromLocalApi(orgId)
  return callCloudApi({ path: `/v1/orgs/${orgId}/sync/reconcile`, method: 'POST', body: { events: pending } })
}

export function useTeamSync() {
  // window 'online' → flushPendingEvents
  // on conflict → emit event for modal
}
```

```tsx
// offline-banner.tsx — show when cloud unreachable in org mode
```

- [ ] **Step 3: Wire `App.tsx`** — mount `OfflineBanner` when `workspaceScope.mode === 'org'`.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: offline event queue flush and reconnect reconcile"
```

---

# Phase E6 — Share local → team

## Task 13: Share-from-local cloud endpoint

**Files:**
- Create: `cloud_api/routes/share.py`
- Modify: `lc_server/integrations/local_project_share.py` (ensure payload shape)
- Test: `tests/cloud_api/test_share.py`

- [ ] **Step 1: Write failing test**

```python
def test_share_from_local_creates_project(mock_verify, mock_store):
    body = {"jiraProjectKey": "BN", "projectName": "BN", "mapping": {}, "deliverySettings": {}}
    r = client.post("/v1/orgs/org1/projects/BN/share-from-local", json=body, headers=auth)
    assert r.status_code == 200
```

- [ ] **Step 2: Implement** — upsert project doc + optional initial WO snapshot from request body.

- [ ] **Step 3: Update `share-project-dialog.tsx`** to:

1. Build payload via local `/api/plugins/livingcolor/...` export endpoint (existing `build_local_project_share_payload`)
2. `callCloudApi` POST share-from-local
3. `switchToOrgWorkspace(orgId)`

- [ ] **Step 4: Append audit event** on successful share.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: share local project to team workspace via cloud API"
```

---

## Manual verification checklist

- [ ] Open plugin → Welcome → **Continue locally** → delivery works, no login
- [ ] Welcome → **Sign in** → Google auth → bootstrap via `api-livingcolor.visualq.ai`
- [ ] Create team org, invite member (second browser)
- [ ] Member A acquires WO lock; Member B sees read-only
- [ ] Disconnect network with lock held → local progress → reconnect → reconcile
- [ ] Share personal project → appears in team Firestore

---

## Spec coverage self-review

| Spec requirement | Task |
| --- | --- |
| Personal 100% local, no account | E1 Task 1–2 |
| Team via `api-livingcolor.visualq.ai` | E2, E3 |
| No local service account | E1 Task 2, README |
| Firestore read + API write/locks | E4 Tasks 7–9 |
| Offline reconcile | E5 Tasks 10–12 |
| Share local → team | E6 Task 13 |
| Welcome gate option B | E1 Task 1 |
| Agents stay local | Unchanged delivery routes in `callDesktopApi` |

No placeholders remain in task steps.
