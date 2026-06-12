# LivingColor Hermes Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete LivingColor plugin integration — Hermes-native inference, MCP opt-in, Firebase/Firestore team workspace, and brand assets — delivered in three ordered phases (A → B → C).

**Architecture:** Phase A removes bootstrap overrides and MCP auto-seed without touching cloud features. Phase B mounts existing `firebase_routes` on the plugin FastAPI router. Phase C ports the desktop Firebase client stack and wires `callDesktopApi` with Bearer tokens. Repo stays external (`~/.hermes/plugins/livingcolor`); no hermes-agent merge required.

**Tech Stack:** Python 3.13, FastAPI, pytest; React 19, Vite, Vitest, Firebase JS SDK v11, Hermes plugin SDK.

**Spec:** `docs/superpowers/specs/2026-06-12-livingcolor-hermes-integration-design.md`

---

## File map (by phase)

| Phase | Create | Modify |
| --- | --- | --- |
| A | `tests/test_bootstrap_inference.py`, `ui/src/lib/jira-dashboard-transport.test.ts` | `lc_server/bootstrap.py`, `lc_server/model_defaults.py`, `lc_server/agent_templates/v1/developer.yaml.tmpl`, `lc_server/agent_templates/v1/publisher.yaml.tmpl`, `ui/src/lib/jira-dashboard-transport.ts`, `tests/lc_server/test_inference_config.py`, `tests/lc_server/test_provisioning.py`, `README.md` |
| B | `tests/test_plugin_firebase_routes.py` | `dashboard/plugin_api.py`, `README.md` |
| C | `ui/public/livingcolor-frog.png`, `ui/public/livingcolor-logo-white.png`, `ui/src/lib/firebase-config.ts`, `ui/src/lib/firebase-config.defaults.ts`, `ui/src/lib/firebase-session-cache.ts`, `ui/src/contexts/firebase-auth-provider.tsx`, `ui/src/components/firebase-auth-gate.tsx`, `ui/src/app/auth/firebase-login-page.tsx`, `ui/src/app/auth/firebase-google-oauth-bridge.tsx`, `ui/src/lib/desktop-api.test.ts`, `ui/src/components/firebase-auth-gate.test.tsx` | `ui/package.json`, `ui/src/services/firebase.ts`, `ui/src/lib/firebase-session.ts`, `ui/src/hooks/use-firebase-auth.ts`, `ui/src/lib/desktop-api.ts`, `ui/src/App.tsx`, `ui/src/main.tsx`, `dashboard/dist/*` (rebuild) |

**Source for Phase C ports:** `agent-lc/apps/desktop/src/` (same relative paths under `ui/src/`).

---

# Phase A — Hermes inference + MCP opt-in

## Task 1: Bootstrap must not mutate Hermes config

**Files:**
- Create: `tests/test_bootstrap_inference.py`
- Modify: `lc_server/bootstrap.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bootstrap_inference.py
"""Bootstrap must not pin OpenRouter or overwrite Hermes model config."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_bootstrap_does_not_call_openrouter_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: anthropic\n  default: claude-sonnet-4-20250514\n",
        encoding="utf-8",
    )

    with patch("lc_server.bundled_credentials.ensure_bundled_openrouter_credentials") as openrouter_mock, patch(
        "lc_server.model_defaults.ensure_livingcolor_fixed_model"
    ) as model_mock:
        from lc_server.bootstrap import bootstrap_livingcolor_server

        bootstrap_livingcolor_server()

    openrouter_mock.assert_not_called()
    model_mock.assert_not_called()

    saved = (tmp_path / "hermes" / "config.yaml").read_text(encoding="utf-8")
    assert "anthropic" in saved
    assert "claude-sonnet-4-20250514" in saved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tamsibesson/programmation/side-projects/livingcolor-plugin && source .venv/bin/activate && pytest tests/test_bootstrap_inference.py -v`

Expected: FAIL — mocks not called because functions are invoked directly.

- [ ] **Step 3: Remove bootstrap overrides**

In `lc_server/bootstrap.py`, delete these lines and their imports:

```python
    from lc_server.bundled_credentials import ensure_bundled_openrouter_credentials
    from lc_server.model_defaults import ensure_livingcolor_fixed_model

    try:
        ensure_bundled_openrouter_credentials()
    except Exception as exc:
        logger.warning("Could not apply bundled OpenRouter credentials: %s", exc)

    try:
        ensure_livingcolor_fixed_model()
    except Exception as exc:
        logger.warning("Could not apply LivingColor fixed model defaults: %s", exc)
```

Keep `is_delivery_llm_available()` usage elsewhere unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bootstrap_inference.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_bootstrap_inference.py lc_server/bootstrap.py
git commit -m "fix: stop pinning OpenRouter model at plugin bootstrap"
```

---

## Task 2: Inference resolves from Hermes config (not LivingColor constants)

**Files:**
- Modify: `lc_server/model_defaults.py`
- Modify: `tests/lc_server/test_inference_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/lc_server/test_inference_config.py`:

```python
def test_developer_inference_uses_hermes_config_when_no_role_defaults(monkeypatch, tmp_path):
    from lc_server.agent_bridge.inference_config import resolve_delivery_inference

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()
    (tmp_path / "hermes" / "config.yaml").write_text(
        "model:\n  provider: anthropic\n  default: claude-sonnet-4-20250514\n",
        encoding="utf-8",
    )

    model, provider = resolve_delivery_inference(
        manifest=None,
        role_default_model=None,
        role_default_provider=None,
        allow_env_override=False,
    )

    assert model == "claude-sonnet-4-20250514"
    assert provider == "anthropic"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/lc_server/test_inference_config.py::test_developer_inference_uses_hermes_config_when_no_role_defaults -v`

Expected: PASS already (logic exists) — this documents intended behavior.

- [ ] **Step 3: Deprecate hardcoded role defaults**

In `lc_server/model_defaults.py`, replace fixed constants with optional fallbacks only:

```python
LIVINGCOLOR_FIXED_PROVIDER: str | None = None
LIVINGCOLOR_FIXED_MODEL: str | None = None
LIVINGCOLOR_DEVELOPER_PROVIDER: str | None = None
LIVINGCOLOR_DEVELOPER_MODEL: str | None = None


def ensure_livingcolor_fixed_model() -> None:
    """No-op — Hermes user config is the sole source of truth."""
```

Remove or no-op `ensure_bundled_openrouter_credentials` callers (already done in Task 1).

Update `test_developer_default_model_is_deepseek` → rename to `test_role_defaults_are_none`:

```python
def test_role_defaults_are_none():
    from lc_server.model_defaults import LIVINGCOLOR_DEVELOPER_MODEL, LIVINGCOLOR_DEVELOPER_PROVIDER

    assert LIVINGCOLOR_DEVELOPER_MODEL is None
    assert LIVINGCOLOR_DEVELOPER_PROVIDER is None
```

Update provisioning tests that assert `manifest.runtime.provider == "openrouter"` to assert provider is empty or inherited from Hermes config in test fixture.

- [ ] **Step 4: Run inference + provisioning tests**

Run: `pytest tests/lc_server/test_inference_config.py tests/lc_server/test_provisioning.py tests/lc_server/test_publisher_template.py -v`

Fix any failures by updating test expectations (not re-adding OpenRouter defaults).

- [ ] **Step 5: Commit**

```bash
git add lc_server/model_defaults.py tests/lc_server/test_inference_config.py tests/lc_server/test_provisioning.py tests/lc_server/test_publisher_template.py
git commit -m "refactor: delivery inference inherits Hermes user provider/model"
```

---

## Task 3: Agent templates without hardcoded provider/model

**Files:**
- Modify: `lc_server/agent_templates/v1/developer.yaml.tmpl`
- Modify: `lc_server/agent_templates/v1/publisher.yaml.tmpl`
- Test: `tests/lc_server/test_hermes_developer_manifest.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/lc_server/test_hermes_developer_manifest.py` (or create if missing):

```python
def test_developer_template_has_no_hardcoded_provider(tmp_path):
    from lc_server.provisioning.template_renderer import render_agent_template

    rendered = render_agent_template("developer", project_key="TEST", project_name="Test")
    assert "provider: openrouter" not in rendered
    assert "model: deepseek" not in rendered
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/lc_server/test_hermes_developer_manifest.py -k hardcoded -v`

- [ ] **Step 3: Edit templates**

Remove these two lines from `runtime:` block in both `developer.yaml.tmpl` and `publisher.yaml.tmpl`:

```yaml
  provider: openrouter
  model: deepseek/deepseek-v4-pro
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add lc_server/agent_templates/v1/developer.yaml.tmpl lc_server/agent_templates/v1/publisher.yaml.tmpl tests/lc_server/test_hermes_developer_manifest.py
git commit -m "refactor: agent templates inherit Hermes inference config"
```

---

## Task 4: MCP strict opt-in (remove Jira auto-seed)

**Files:**
- Modify: `ui/src/lib/jira-dashboard-transport.ts`
- Create: `ui/src/lib/jira-dashboard-transport.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// ui/src/lib/jira-dashboard-transport.test.ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/hermes', () => ({
  connectJiraMcp: vi.fn(async () => ({ ok: true, message: 'ok' })),
  getLivingColorConfigRecord: vi.fn(async () => ({ mcp_servers: {} })),
  saveMcpServerConfig: vi.fn(async () => ({ ok: true })),
}))

import { connectJiraViaMcp } from './jira-dashboard-transport'
import { saveMcpServerConfig } from '@/hermes'

describe('connectJiraViaMcp', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not auto-save MCP preset without user credentials', async () => {
    await connectJiraViaMcp()
    expect(saveMcpServerConfig).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd ui && npm test -- src/lib/jira-dashboard-transport.test.ts`

Expected: FAIL — `saveMcpServerConfig` called by `ensureJiraMcpStdioConfigured`.

- [ ] **Step 3: Remove auto-seed**

In `ui/src/lib/jira-dashboard-transport.ts`:

1. Delete function `ensureJiraMcpStdioConfigured` entirely.
2. In `connectJiraViaMcp`, remove the `await ensureJiraMcpStdioConfigured()` line.

`connectJiraViaCredentials` keeps `persistJiraMcpConfig` — that is explicit user action.

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Rebuild dist (optional for Phase A, required before release)**

Run: `cd ui && npm run build`

- [ ] **Step 6: Commit**

```bash
git add ui/src/lib/jira-dashboard-transport.ts ui/src/lib/jira-dashboard-transport.test.ts
git commit -m "fix: remove automatic Jira MCP preset seeding"
```

---

## Task 5: Phase A docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README prerequisites**

Add section:

```markdown
## LLM provider

LivingColor uses whatever provider and model you configured in Hermes
(`~/.hermes/config.yaml` → `model.provider` / `model.default`). The plugin
does not bundle or override OpenRouter credentials.

## MCP (Jira / GitLab)

Configure MCP servers yourself via Hermes (`hermes mcp` or dashboard MCP
settings). LivingColor only reads connection status and scopes per-project
configs after you explicitly save credentials in Project → Integrations.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document Hermes-owned LLM and MCP setup"
```

---

## Phase A exit gate

Run: `pytest tests/test_bootstrap_inference.py tests/lc_server/test_inference_config.py -v && cd ui && npm test`

All green before starting Phase B.

---

# Phase B — Firebase backend wiring

## Task 6: Mount Firebase router on plugin API

**Files:**
- Modify: `dashboard/plugin_api.py`
- Create: `tests/test_plugin_firebase_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plugin_firebase_routes.py
"""Firebase routes are mounted under the plugin prefix."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_client_config_route_is_mounted():
    from dashboard.plugin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)

    response = client.get("/api/plugins/livingcolor/firebase/client-config")
    assert response.status_code == 200
    body = response.json()
    assert "enabled" in body
```

- [ ] **Step 2: Run test — expect FAIL (404)**

Run: `pytest tests/test_plugin_firebase_routes.py -v`

- [ ] **Step 3: Mount router**

In `dashboard/plugin_api.py`:

```python
from lc_server.api.firebase_routes import router as firebase_router

router.include_router(delivery_router, prefix="/delivery")
router.include_router(jira_router, prefix="/jira")
router.include_router(firebase_router, prefix="/firebase")
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add dashboard/plugin_api.py tests/test_plugin_firebase_routes.py
git commit -m "feat: mount Firebase API routes on LivingColor plugin router"
```

---

## Task 7: Firebase client-config with embedded defaults

**Files:**
- Modify: `tests/test_plugin_firebase_routes.py`
- Modify: `lc_server/integrations/firebase_auth.py` (only if test reveals gap)

- [ ] **Step 1: Write test for embedded web config fallback**

```python
def test_client_config_returns_embedded_defaults_when_env_set(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_FIREBASE_API_KEY", "AIzaSy-test")
    monkeypatch.setenv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", "livingcolor-app")

    from dashboard.plugin_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/livingcolor")
    client = TestClient(app)

    response = client.get("/api/plugins/livingcolor/firebase/client-config")
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["projectId"] == "livingcolor-app"
```

- [ ] **Step 2: Run and fix until PASS**

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugin_firebase_routes.py
git commit -m "test: firebase client-config exposes livingcolor-app defaults"
```

---

## Task 8: Phase B README — Firebase admin setup

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add Firebase admin section**

```markdown
## Firebase (team workspaces)

Team collaboration requires Firebase Admin credentials on the machine running
the Hermes dashboard:

```bash
# ~/.hermes/livingcolor/.env
FIREBASE_SERVICE_ACCOUNT_PATH=~/.hermes/livingcolor/firebase-sa.json
```

Download the service account JSON from the Firebase console (`livingcolor-app`
project). Restart `hermes dashboard` after adding the file.

Public web client config is embedded (safe to expose). Security is enforced
by Firebase Auth + Firestore rules + verified ID tokens on API routes.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: Firebase admin setup for team workspaces"
```

---

## Phase B exit gate

Run: `pytest tests/test_plugin_firebase_routes.py tests/lc_server/test_firebase_auth.py tests/lc_server/test_firestore_collaboration.py -v`

---

# Phase C — Firebase UI, workspace, branding

## Task 9: Add Firebase npm dependency

**Files:**
- Modify: `ui/package.json`

- [ ] **Step 1: Install firebase**

Run: `cd ui && npm install firebase@^11.0.0`

- [ ] **Step 2: Commit**

```bash
git add ui/package.json ui/package-lock.json
git commit -m "chore: add Firebase JS SDK for plugin auth"
```

---

## Task 10: Port Firebase config defaults

**Files:**
- Create: `ui/src/lib/firebase-config.defaults.ts`
- Create: `ui/src/lib/firebase-config.ts`

Copy from `agent-lc/apps/desktop/src/lib/firebase-config.defaults.ts` and `firebase-config.ts`.

Adjust imports: `@/lib/firebase-config.defaults`, `@/lib/firebase-session` (`fetchFirebaseClientConfig`).

Resolution order unchanged: Vite env → backend `/firebase/client-config` → `LIVINGCOLOR_CLOUD_FIREBASE_CONFIG`.

- [ ] **Step 1: Copy files verbatim (fix import paths only)**

- [ ] **Step 2: Commit**

```bash
git add ui/src/lib/firebase-config.ts ui/src/lib/firebase-config.defaults.ts
git commit -m "feat: port Firebase web config resolution for Hermes plugin"
```

---

## Task 11: Port Firebase client service

**Files:**
- Modify: `ui/src/services/firebase.ts`

Copy from `agent-lc/apps/desktop/src/services/firebase.ts`.

Remove Electron-only branches (`isElectronShell`, `window.livingColorDesktop`) — Hermes tab is always browser:

```typescript
function isElectronShell(): boolean {
  return false
}
```

- [ ] **Step 1: Port and simplify for browser-only**

- [ ] **Step 2: Commit**

```bash
git add ui/src/services/firebase.ts
git commit -m "feat: enable Firebase client auth in plugin UI"
```

---

## Task 12: Port firebase-session + cache (replace stubs)

**Files:**
- Create: `ui/src/lib/firebase-session-cache.ts`
- Modify: `ui/src/lib/firebase-session.ts`

Copy from agent-lc desktop. `firebase-session.ts` uses `callDesktopApi` — paths stay `/api/firebase/...` (rewriter added in Task 13).

Add `fetchFirebaseClientConfig`:

```typescript
export async function fetchFirebaseClientConfig(): Promise<FirebaseClientConfigResponse> {
  return callDesktopApi({ path: '/api/firebase/client-config' })
}
```

- [ ] **Step 1: Port files**

- [ ] **Step 2: Commit**

```bash
git add ui/src/lib/firebase-session.ts ui/src/lib/firebase-session-cache.ts
git commit -m "feat: port Firebase session API client"
```

---

## Task 13: Extend callDesktopApi with Firebase paths and Bearer token

**Files:**
- Modify: `ui/src/lib/desktop-api.ts`
- Create: `ui/src/lib/desktop-api.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { $firebaseIdToken } from '@/store/firebase-auth'

describe('callDesktopApi', () => {
  beforeEach(() => {
    $firebaseIdToken.set('test-token')
    ;(window as any).__HERMES_PLUGIN_SDK__ = {
      fetchJSON: vi.fn(async () => ({})),
    }
  })

  it('rewrites firebase paths and sends Authorization header', async () => {
    const { callDesktopApi } = await import('./desktop-api')
    await callDesktopApi({ path: '/api/firebase/bootstrap', method: 'POST' })

    const sdk = (window as any).__HERMES_PLUGIN_SDK__
    expect(sdk.fetchJSON).toHaveBeenCalledWith(
      '/api/plugins/livingcolor/firebase/bootstrap',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      }),
    )
  })
})
```

- [ ] **Step 2: Implement**

```typescript
import { $firebaseActiveOrgId, $firebaseIdToken } from '@/store/firebase-auth'
import { $apiOrgId, $apiProjectKey, LOCAL_ORG_ID } from '@/store/project-api-context'
import { getFirebaseIdToken } from '@/services/firebase'
import { setFirebaseIdToken } from '@/store/firebase-auth'

function rewrite(path: string): string {
  return path
    .replace(/^\/api\/delivery\//, '/api/plugins/livingcolor/delivery/')
    .replace(/^\/api\/jira\//, '/api/plugins/livingcolor/jira/')
    .replace(/^\/api\/firebase\//, '/api/plugins/livingcolor/firebase/')
}

function buildHeaders(init: RequestInit): Headers {
  const headers = new Headers(init.headers)
  const token = $firebaseIdToken.get()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
    const orgId = $firebaseActiveOrgId.get() || ($apiOrgId.get() !== LOCAL_ORG_ID ? $apiOrgId.get() : null)
    if (orgId) headers.set('x-lc-org-id', orgId)
  }
  const projectKey = $apiProjectKey.get()
  if (projectKey) headers.set('x-lc-project-key', projectKey)
  return headers
}
```

Wire `buildHeaders` into `callDesktopApi`; add token refresh retry on 401/403 (mirror agent-lc `desktop-api.ts`).

Org/project headers: `x-lc-org-id` and `x-lc-project-key` (see `lc_server/middleware.py`).

- [ ] **Step 3: Run test — PASS**

- [ ] **Step 4: Commit**

```bash
git add ui/src/lib/desktop-api.ts ui/src/lib/desktop-api.test.ts
git commit -m "feat: attach Firebase bearer token to plugin API calls"
```

---

## Task 14: Port FirebaseAuthProvider and gate

**Files:**
- Create: `ui/src/contexts/firebase-auth-provider.tsx`
- Create: `ui/src/components/firebase-auth-gate.tsx`
- Create: `ui/src/app/auth/firebase-login-page.tsx`
- Create: `ui/src/app/auth/firebase-google-oauth-bridge.tsx` (if popup redirect needed)
- Modify: `ui/src/hooks/use-firebase-auth.ts`

Copy from agent-lc desktop. `use-firebase-auth.ts` becomes:

```typescript
import { useContext } from 'react'
import { FirebaseAuthReactContext, type FirebaseAuthContextValue } from '@/contexts/firebase-auth-context'

export function useFirebaseAuth(): FirebaseAuthContextValue {
  const ctx = useContext(FirebaseAuthReactContext)
  if (!ctx) throw new Error('useFirebaseAuth must be used within FirebaseAuthProvider')
  return ctx
}
```

- [ ] **Step 1: Port provider + gate + login page**

- [ ] **Step 2: Write gate test**

```typescript
// ui/src/components/firebase-auth-gate.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { FirebaseAuthGate } from './firebase-auth-gate'

vi.mock('@/hooks/use-firebase-auth', () => ({
  useFirebaseAuth: () => ({ enabled: true, status: 'signed-out' }),
}))
vi.mock('@/app/auth/firebase-login-page', () => ({
  FirebaseLoginPage: () => <div>Login page</div>,
}))

it('shows login when signed out and firebase enabled', () => {
  render(<FirebaseAuthGate><div>App</div></FirebaseAuthGate>)
  expect(screen.getByText('Login page')).toBeTruthy()
})
```

- [ ] **Step 3: Run vitest — PASS**

- [ ] **Step 4: Commit**

```bash
git add ui/src/contexts/firebase-auth-provider.tsx ui/src/components/firebase-auth-gate.tsx ui/src/app/auth/ ui/src/hooks/use-firebase-auth.ts ui/src/components/firebase-auth-gate.test.tsx
git commit -m "feat: port Firebase auth provider and login gate"
```

---

## Task 15: Wire App shell

**Files:**
- Modify: `ui/src/App.tsx`
- Modify: `ui/src/main.tsx` (if provider must wrap outside router)

- [ ] **Step 1: Wrap DeliveryApp**

```tsx
import { FirebaseAuthProvider } from '@/contexts/firebase-auth-provider'
import { FirebaseAuthGate } from '@/components/firebase-auth-gate'

export default function App() {
  // ... existing apiOk check ...
  return (
    <FirebaseAuthProvider>
      <FirebaseAuthGate>
        <DeliveryApp />
      </FirebaseAuthGate>
    </FirebaseAuthProvider>
  )
}
```

When `enabled === false`, `FirebaseAuthGate` should show setup banner (port logic from provider: check `fetchFirebaseClientConfig`).

- [ ] **Step 2: Manual smoke**

1. Start dashboard without Firebase admin → setup banner.
2. Add `FIREBASE_SERVICE_ACCOUNT_PATH` → login page appears.

- [ ] **Step 3: Commit**

```bash
git add ui/src/App.tsx
git commit -m "feat: gate LivingColor tab behind Firebase auth when configured"
```

---

## Task 16: Logo assets

**Files:**
- Create: `ui/public/livingcolor-frog.png`
- Create: `ui/public/livingcolor-logo-white.png`

- [ ] **Step 1: Copy assets**

Source: agent-lc desktop `public/` or design assets. If not in git, export from desktop build:

```bash
cp /path/to/agent-lc/apps/desktop/public/livingcolor-frog.png ui/public/
cp /path/to/agent-lc/apps/desktop/public/livingcolor-logo-white.png ui/public/
```

- [ ] **Step 2: Verify sidebar renders**

`project-workspace-layout.tsx` already uses `brandAssetPath('livingcolor-frog.png')` — Vite serves `public/` at plugin base URL.

- [ ] **Step 3: Add logo to login page** (in `firebase-login-page.tsx` port)

- [ ] **Step 4: Commit**

```bash
git add ui/public/livingcolor-frog.png ui/public/livingcolor-logo-white.png ui/src/app/auth/firebase-login-page.tsx
git commit -m "feat: add LivingColor brand assets to plugin UI"
```

---

## Task 17: Rebuild bundle and final verification

**Files:**
- Modify: `dashboard/dist/index.js`, `dashboard/dist/style.css`

- [ ] **Step 1: Build**

Run: `cd ui && npm run build && npm test`

- [ ] **Step 2: Python suite (fast dev scope)**

Run: `pytest tests/test_bootstrap_inference.py tests/test_plugin_firebase_routes.py tests/lc_server/test_firebase_auth.py -v`

- [ ] **Step 3: Commit dist**

```bash
git add dashboard/dist/
git commit -m "build: rebuild plugin UI bundle with Firebase and branding"
```

---

## Phase C exit gate (manual)

1. `hermes plugins enable livingcolor` + restart dashboard
2. Without Firebase admin → setup instructions visible
3. With admin + sign-in → org switcher works, create team, Personal vs Team toggle
4. Delivery overview loads under Personal workspace
5. Integrations does not auto-write MCP on page load

---

## Plan self-review

| Spec requirement | Task |
| --- | --- |
| Remove OpenRouter bootstrap | Task 1 |
| Templates inherit Hermes config | Task 3 |
| MCP opt-in strict | Task 4 |
| Mount `/firebase/*` | Task 6 |
| Firebase admin docs | Task 8 |
| Port Firebase UI stack | Tasks 9–15 |
| callDesktopApi Bearer + rewrite | Task 13 |
| Logo assets | Task 16 |
| External repo (no hermes merge) | Architecture header (documented) |

No TBD placeholders. Header names for org/project must be verified against `lc_server/middleware.py` during Task 13 implementation.
