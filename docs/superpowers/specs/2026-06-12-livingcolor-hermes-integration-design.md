# LivingColor Hermes Plugin — Integration Design (Firebase, Inference, MCP, Workspace, Branding)

**Date:** 2026-06-12  
**Status:** Approved (2026-06-12 — user validated)  
**Build strategy:** Ordered phases (A → B → C)  
**Parent spec:** agent-lc `docs/superpowers/specs/2026-06-12-livingcolor-hermes-plugin-design.md`

## Summary

Complete the LivingColor Hermes plugin integration after the initial port: reconnect Firebase/Firestore team collaboration, respect the user's Hermes inference provider (no bundled OpenRouter), enforce strict opt-in MCP configuration, restore workspace/org UX, and ship LivingColor brand assets. Work is delivered in three ordered phases so each slice is reviewable and testable independently.

## Decisions (brainstorming)

| Topic | Decision |
| --- | --- |
| Firebase hosting | Shared LivingColor cloud project `livingcolor-app` (public web config embedded; admin credentials via env) |
| Access model | Desktop parity — Firebase login required when server admin is configured; after sign-in, user picks Personal (local SQLite) or Team (Firestore) |
| MCP policy | Strict opt-in — plugin never writes `mcp_servers` without explicit user action |
| Inference | Use Hermes `config.yaml` provider/model chosen by the user; remove OpenRouter bootstrap |
| Implementation order | Phased delivery: A (inference + MCP) → B (Firebase backend) → C (Firebase UI + workspace + logo) |
| Tab nav icon | Hermes manifest stays Lucide-only (`Palette`); brand logo lives inside the plugin (sidebar + login) |

## Goals

- Team/workspace collaboration works in the Hermes dashboard tab the same way it does in the Electron desktop app.
- Delivery agents run on whatever LLM provider the user configured in Hermes — no silent override to OpenRouter/DeepSeek.
- Users own their Jira/GitLab MCP setup; LivingColor only reads status and scopes per-project configs after explicit configuration.
- LivingColor branding is visible inside the plugin shell (sidebar, login page).

## Non-goals

- No changes to `hermes-agent` upstream (custom tab icons, host auth bridge, etc.).
- No bundled secrets (OpenRouter keys, MCP tokens, Firebase service account JSON in the repo).
- No Firebase BYO / custom project support in v1 (cloud `livingcolor-app` only; overrides deferred).
- No unauthenticated local-only mode when Firebase admin is configured (desktop parity).
- No redesign of Mission Control UI beyond Hermes-native CSS already applied.

## Current gaps

1. **Firebase routes not mounted** — `lc_server/api/firebase_routes.py` exists but `dashboard/plugin_api.py` only mounts `/delivery` and `/jira`.
2. **UI stubs** — `services/firebase.ts`, `hooks/use-firebase-auth.ts`, `lib/firebase-session.ts` return disabled/errors.
3. **OpenRouter forced at bootstrap** — `ensure_bundled_openrouter_credentials()` and `ensure_livingcolor_fixed_model()` in `lc_server/bootstrap.py`.
4. **Templates hardcode OpenRouter** — `lc_server/agent_templates/v1/*.yaml.tmpl` set `provider: openrouter` and `model: deepseek/deepseek-v4-pro`.
5. **MCP auto-seed** — `ensureJiraMcpStdioConfigured()` in `ui/src/lib/jira-dashboard-transport.ts` writes Jira MCP preset without explicit opt-in.
6. **Missing logo assets** — `project-workspace-layout.tsx` references PNGs not present under `ui/public/`.

---

## Architecture

```text
Hermes dashboard tab (/livingcolor)
  └─ FirebaseAuthGate (when admin configured)
       └─ Mission Control UI (workspace sidebar, org switcher, delivery views)
            ⇄ callDesktopApi → SDK fetchJSON
                 /api/plugins/livingcolor/delivery/*
                 /api/plugins/livingcolor/jira/*
                 /api/plugins/livingcolor/firebase/*  (+ Bearer Firebase ID token)

Hermes config.yaml (user-owned)
  └─ model.provider / model.default  ← sole source for delivery agent inference

Hermes mcp_servers (user-owned)
  └─ jira / gitlab  ← configured explicitly; LivingColor scopes per project only

~/.hermes/livingcolor/
  ├─ runtime.db, project_mapping.yaml     (local / personal workspace)
  └─ .env (FIREBASE_SERVICE_ACCOUNT_PATH, optional overrides)

Firebase livingcolor-app (cloud)
  └─ Firestore orgs, members, shared project configs
```

---

## Phase A — Hermes inference + MCP opt-in

**Purpose:** Stop overriding user infrastructure before enabling cloud features.

### A.1 Remove OpenRouter bootstrap

- Delete calls to `ensure_bundled_openrouter_credentials()` and `ensure_livingcolor_fixed_model()` from `lc_server/bootstrap.py`.
- Keep `is_delivery_llm_available()` and prerequisites checks; surface clear errors when Hermes has no configured provider.
- Update `tests/lc_server/test_env_loader.py` and `test_inference_config.py` to reflect non-mutating bootstrap.
- README: document that users must configure their LLM provider in Hermes (`hermes config` / dashboard Settings).

### A.2 Agent templates inherit Hermes config

- Remove `provider` and `model` from runtime blocks in `lc_server/agent_templates/v1/*.yaml.tmpl` (developer, publisher, analyst, planner, orchestrator as applicable).
- `resolve_delivery_inference()` already falls through to `load_config()` — no logic change required beyond template defaults.
- Existing provisioned manifests under `projects/{KEY}/agents/` retain stored values until re-provisioned; document one-time `upgrade_all_project_manifests` behavior if templates change checksums.

### A.3 MCP strict opt-in (UI)

- Remove `ensureJiraMcpStdioConfigured()` and any call sites that auto-persist preset configs on connect.
- `connectJiraViaCredentials` / `connectGitlabViaCredentials` only call `saveMcpServerConfig` after the user submits the credentials dialog.
- Integrations screen: when MCP missing, show status + pointer to Hermes MCP settings (no silent write).
- Add/update Vitest: connecting Jira without prior config does not mutate config record.

### A.4 Tests (Phase A exit criteria)

- `pytest tests/lc_server/test_inference_config.py` — resolves from Hermes config, not LivingColor constants.
- Bootstrap test: starting plugin does not modify `~/.hermes/config.yaml`.
- `npm test` — jira-dashboard-transport no auto-seed.

---

## Phase B — Firebase backend wiring

**Purpose:** Expose Firestore APIs on the plugin router with correct server-side auth.

### B.1 Mount Firebase router

```python
# dashboard/plugin_api.py
from lc_server.api.firebase_routes import router as firebase_router
router.include_router(firebase_router, prefix="/firebase")
```

Routes become `/api/plugins/livingcolor/firebase/*` (bootstrap, me, orgs, preferences, projects, members, invites).

### B.2 Server configuration

Firebase admin enabled when any of:

- `FIREBASE_SERVICE_ACCOUNT_PATH` or `GOOGLE_APPLICATION_CREDENTIALS` points to a valid JSON file
- Inline triplet: `FIREBASE_CLIENT_EMAIL` + `FIREBASE_PRIVATE_KEY` + `FIREBASE_PROJECT_ID`

Default project ID: `livingcolor-app` (matches embedded web config).

`GET /firebase/client-config` returns `{ enabled, config }` where `config` comes from `client_firebase_config()` (env `NEXT_PUBLIC_FIREBASE_*` with fallback to embedded defaults).

### B.3 Middleware / headers

Reuse existing `lc_server/middleware.py` patterns for:

- `Authorization: Bearer <Firebase ID token>`
- Org scope header (same as desktop IPC: active org id)

Verify Firebase routes receive tokens through the Hermes dashboard auth middleware (session token for loopback) **and** Firebase bearer for Firestore operations — two layers, same as agent-lc.

### B.4 Degraded mode when admin missing

If `firebase_admin_configured()` is false:

- `GET /firebase/client-config` → `{ enabled: false, config: null }`
- UI Phase C shows setup banner (not login form).

### B.5 Tests (Phase B exit criteria)

- `tests/lc_server/test_firebase_auth.py`, `test_firestore_collaboration.py` against plugin router prefix.
- Smoke: `client-config` returns embedded web config when admin credentials present in test env.

---

## Phase C — Firebase UI, workspace, branding

**Purpose:** Restore full desktop collaboration UX inside the Hermes tab.

### C.1 Port Firebase client stack from agent-lc desktop

Copy/adapt (paths adjusted for plugin):

| Source (agent-lc desktop) | Target (livingcolor-plugin ui) |
| --- | --- |
| `services/firebase.ts` | `ui/src/services/firebase.ts` |
| `lib/firebase-config.ts` | `ui/src/lib/firebase-config.ts` |
| `lib/firebase-config.defaults.ts` | `ui/src/lib/firebase-config.defaults.ts` |
| `lib/firebase-session.ts` | `ui/src/lib/firebase-session.ts` (replace stub) |
| `lib/firebase-session-cache.ts` | `ui/src/lib/firebase-session-cache.ts` |
| `contexts/firebase-auth-provider.tsx` | `ui/src/contexts/firebase-auth-provider.tsx` |
| `app/auth/firebase-login-page.tsx` | `ui/src/app/auth/firebase-login-page.tsx` |
| `app/auth/firebase-google-oauth-bridge.tsx` | if needed for popup/redirect in browser |
| `components/firebase-auth-gate.tsx` | `ui/src/components/firebase-auth-gate.tsx` |

Add `firebase` npm dependency to `ui/package.json`.

### C.2 Extend `callDesktopApi`

```typescript
// ui/src/lib/desktop-api.ts
function rewrite(path: string): string {
  return path
    .replace(/^\/api\/delivery\//, '/api/plugins/livingcolor/delivery/')
    .replace(/^\/api\/jira\//, '/api/plugins/livingcolor/jira/')
    .replace(/^\/api\/firebase\//, '/api/plugins/livingcolor/firebase/')
}
```

Attach headers from `$firebaseIdToken`, `$firebaseActiveOrgId`, `$apiProjectKey` (mirror agent-lc `desktop-api.ts`). Retry once with refreshed token on 401/403 Firebase errors.

### C.3 App shell wiring

```tsx
// ui/src/App.tsx (conceptual)
<FirebaseAuthProvider>
  <FirebaseAuthGate>
    <DeliveryApp />
  </FirebaseAuthGate>
</FirebaseAuthProvider>
```

When `enabled === false` (admin not configured): render setup instructions, not children.

Workspace components already present — no structural change:

- `WorkspaceOrgSwitcher`, `workspace-sidebar-user-menu`, `share-project-dialog`
- `ProjectWorkspaceProvider` local/cloud merge

### C.4 Logo assets

- Add `ui/public/livingcolor-frog.png` and `ui/public/livingcolor-logo-white.png` (copy from agent-lc desktop build assets).
- `vite.config.ts` `base` ensures `brandAssetPath()` resolves in plugin bundle.
- Login page: centered logo.
- Sidebar: existing `LivingColorBrandMark` component.

Manifest `icon: "Palette"` unchanged (Hermes limitation).

### C.5 Tests (Phase C exit criteria)

- Vitest: `FirebaseAuthGate` redirects signed-out users to login when enabled.
- Vitest: `callDesktopApi` adds Bearer header for `/api/firebase/*` paths.
- Vitest: org switcher renders team list when mock auth returns organizations.
- Manual: sign in → create team → share project → visible in Firestore.

---

## Error handling

| Condition | Behavior |
| --- | --- |
| Firebase admin not configured | Setup banner with env var instructions; no login loop |
| Firebase configured, user signed out | `FirebaseLoginPage` blocks app |
| Invalid/expired ID token | Refresh once; on failure, sign out and return to login |
| Hermes LLM not configured | Prerequisites panel lists `llm_model` missing; no OpenRouter fallback |
| Jira/GitLab MCP missing | Prerequisites + Integrations UI; no auto-write |
| Email not verified | 403 from server; surface message on login |

---

## Configuration reference

Example `~/.hermes/livingcolor/.env`:

```bash
# Required for team/workspace (Phase B+)
FIREBASE_SERVICE_ACCOUNT_PATH=~/.hermes/livingcolor/firebase-sa.json

# Optional — defaults to livingcolor-app embedded web config
# NEXT_PUBLIC_FIREBASE_PROJECT_ID=livingcolor-app
```

Hermes LLM (user responsibility):

```yaml
# ~/.hermes/config.yaml
model:
  provider: <user choice>
  default: <user model>
```

MCP (user responsibility via `hermes mcp` or dashboard MCP UI) — LivingColor never seeds defaults.

---

## Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Google OAuth popup blocked in dashboard browser | Use `signInWithPopup` with fallback redirect bridge (port desktop bridge) |
| Firebase + Hermes dual auth confusion | Document: Hermes session protects HTTP transport; Firebase bearer identifies LivingColor user |
| Existing users with OpenRouter-pinned config | Phase A stops mutating config; users manually switch provider in Hermes |
| Large Phase C port | Ordered after A/B; Firebase UI isolated from inference changes |
| Logo assets not in git (desktop) | Obtain from design source or agent-lc release artifacts; block Phase C on asset availability |

---

## Phase delivery checklist

| Phase | Ships | User-visible outcome |
| --- | --- | --- |
| **A** | Inference + MCP cleanup | Delivery uses Hermes model; MCP not auto-written |
| **B** | Firebase API mounted | `curl /api/plugins/livingcolor/firebase/client-config` works |
| **C** | Full auth + workspace + logo | Login, teams, shared projects, branded sidebar |

Each phase merges independently; Phase B does not require Phase C UI to test (curl/pytest). Phase C depends on Phase B.
