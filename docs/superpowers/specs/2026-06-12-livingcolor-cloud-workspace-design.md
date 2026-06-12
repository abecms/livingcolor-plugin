# LivingColor Cloud Workspace — Design

**Date:** 2026-06-12  
**Status:** Approved (2026-06-12)  
**Parent spec:** `docs/superpowers/specs/2026-06-12-livingcolor-hermes-integration-design.md`  
**API host:** `https://api-livingcolor.visualq.ai`

## Summary

Split LivingColor into two clear usage modes inside the Hermes plugin:

1. **Personal (default)** — 100% local: delivery state in SQLite (`~/.hermes/livingcolor/runtime.db`), no account required.
2. **Team** — shared workspace backed by Firebase `livingcolor-app` Firestore, accessed **without** storing Firebase admin credentials on the user's machine.

Team mode uses a **LivingColor cloud API** at `https://api-livingcolor.visualq.ai` as the only holder of the Firebase service account. End users authenticate with Firebase Auth (Google/email); the plugin never ships or reads a service-account JSON locally.

Delivery agents always run on the user's local Hermes instance. Cloud stores shared config, work-order state, locks, and audit/events — not agent execution.

## Decisions (brainstorming 2026-06-12)

| Topic | Decision |
| --- | --- |
| Cloud hosting | LivingColor API at `https://api-livingcolor.visualq.ai` holds Firebase Admin credentials |
| Data scope (team) | Shared: org membership, project config, WO state, gates, queue, logs/audit/events. Agents remain local |
| Local UX | Welcome screen: **Continue locally** (default) or **Sign in to collaborate** — no account required for personal |
| Sync model | Firestore read (UI listeners) + cloud API for writes and WO locks; non-lock-holders read-only |
| Offline (team) | Allow local progress on locked WOs; queue events locally; reconcile on reconnect with conflict alerts |
| API base URL | `https://api-livingcolor.visualq.ai` (not `api.livingcolor.app`) |
| Deprecate local SA | Remove user-facing requirement for `FIREBASE_SERVICE_ACCOUNT_PATH` in `~/.hermes/livingcolor/.env` |

## Goals

- Personal mode works out of the box with zero cloud configuration.
- Team members join shared projects by signing in — no service account on their laptop.
- Multiple team members see shared delivery state in near real time.
- Only the machine/user holding a WO lock can mutate that WO; others see read-only UI.
- Offline work on locked WOs is possible with explicit reconciliation after reconnect.

## Non-goals (v1)

- Cloud-hosted agent execution (workers in the cloud).
- BYO Firebase project / self-hosted team API (enterprise override deferred).
- Replacing Hermes core DB — LivingColor continues to use `~/.hermes/livingcolor/runtime.db` for local execution.
- App Check / abuse hardening beyond Firebase Auth + API authorization (phase 2).

## Architecture

```text
Hermes dashboard — LivingColor plugin
┌──────────────────────────────────────────────────────────────┐
│ Welcome gate                                                 │
│   [ Continue locally ]  ──▶ Personal workspace               │
│   [ Sign in to collaborate ] ──▶ Firebase Auth               │
│                                                                  │
│ Personal: SQLite only, local agents, no cloud calls            │
│                                                                  │
│ Team:                                                            │
│   UI reads  ──▶ Firestore (Firebase Auth + security rules)     │
│   UI + Python writes/locks ──▶ api-livingcolor.visualq.ai      │
│   Delivery engine ──▶ runtime.db (local cache + execution)     │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  https://api-livingcolor.visualq.ai     │
        │  - Verifies Firebase ID tokens          │
        │  - Holds service account (platform secret)│
        │  - WO locks, event append, reconcile    │
        │  - Org/project CRUD, invites            │
        └─────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  Firebase livingcolor-app               │
        │  Auth + Firestore                       │
        └─────────────────────────────────────────┘
```

### Recommended integration pattern (v1)

**Hybrid read/write split** (approach 2 from brainstorming):

- **Reads:** Firestore client SDK in the plugin UI (real-time listeners, user token).
- **Writes / locks / privileged ops:** Cloud API only (Admin SDK server-side).
- **Local Python delivery runtime:** Calls cloud API for team-scoped mutations; never initializes Firebase Admin locally in production.

## Authentication model

| Asset | Location | Secret? |
| --- | --- | --- |
| Firebase web client config | Embedded in plugin | No — public by design |
| User session (Firebase ID token) | Browser `localStorage` / plugin session cache | Transient |
| Firebase service account JSON | Cloud platform secrets only | Yes — never in repo or `~/.hermes` |

### Request auth

All cloud API calls from the plugin:

```http
Authorization: Bearer <firebase_id_token>
X-LC-Org-Id: <active_org_id>        # team scope only
X-LC-Project-Key: <jira_project_key> # when project-scoped
```

Cloud API validates token, checks org membership, enforces lock ownership on mutations.

### Deprecation of local Firebase admin routes

`GET /api/plugins/livingcolor/firebase/*` on the Hermes plugin router:

- **Production team flows** → `https://api-livingcolor.visualq.ai/v1/...`
- Local `firebase_routes.py` may remain for **dev/staging** behind `LIVINGCOLOR_CLOUD_API_URL` override, but must not be required for end users.

## Data boundaries

| Data | Personal (local) | Team (cloud) |
| --- | --- | --- |
| Work orders, gates, readiness queue | SQLite only | Firestore + SQLite cache |
| `project_mapping`, delivery settings | Local YAML/DB | Firestore `orgs/{orgId}/projects/{key}` |
| Organizations, members, invites | — | Firestore |
| Audit / delivery events | SQLite (local only) | Firestore append-only `events` |
| Agent execution | Local Hermes | Local Hermes (unchanged) |

### Share local → team

User action **Share with team** on a personal project:

1. Upload project config + initial WO snapshot via cloud API.
2. Switch workspace scope to `{ mode: 'org', orgId }`.
3. Subsequent reads subscribe to Firestore; writes go through API + lock protocol.

## Work-order lock protocol

1. **Acquire** — `POST /v1/orgs/{orgId}/work-orders/{id}/lock`  
   Success grants write rights on that WO for this user/device session.
2. **Execute** — local delivery engine advances WO in `runtime.db`.
3. **Emit events** — each state transition → `POST /v1/orgs/{orgId}/events` (append-only).
4. **Release** — `DELETE /v1/orgs/{orgId}/work-orders/{id}/lock`  
   Firestore updated; other members return to read-only on that WO.
5. **Observe** — UI Firestore listeners; local Python refreshes cache via periodic sync or post-event webhook (v1: polling acceptable).

Non-lock-holders: read-only UI (disabled actions, tooltip showing lock owner).

## Offline behavior

When `api-livingcolor.visualq.ai` is unreachable:

| State | Behavior |
| --- | --- |
| User holds WO lock (acquired before outage) | May continue local execution; events queued in SQLite `pending_events` |
| User does not hold lock | Read cached SQLite/Firestore snapshot; banner **Offline — read only** |
| Reconnect | Flush `pending_events` → `POST /v1/orgs/{orgId}/sync/reconcile` |
| Conflict (cloud diverged) | Surface alert + diff; no silent overwrite |

## UX — welcome gate

Replace the current **Firebase admin required** banner.

```
┌─────────────────────────────────────┐
│  [LivingColor logo]                 │
│                                     │
│  [ Continue locally ]    ← default  │
│  [ Sign in to collaborate ]         │
└─────────────────────────────────────┘
```

- **Continue locally** → `workspaceScope = { mode: 'local' }`, full plugin, no Firebase.
- **Sign in to collaborate** → Firebase Auth → org switcher (Personal / Team orgs).
- Signed-in users can switch back to Personal without signing out.

## Cloud API surface (v1)

Base URL: `https://api-livingcolor.visualq.ai`

```
# Session & config
GET  /v1/health
GET  /v1/config/firebase-client          # optional mirror of embedded config
POST /v1/session/bootstrap               # { user, organizations }

# Organizations
GET  /v1/orgs
POST /v1/orgs
GET  /v1/orgs/{orgId}/members
POST /v1/orgs/{orgId}/invites

# Projects
GET  /v1/orgs/{orgId}/projects
POST /v1/orgs/{orgId}/projects
PATCH /v1/orgs/{orgId}/projects/{key}
POST /v1/orgs/{orgId}/projects/{key}/share-from-local

# Work orders & locks
GET  /v1/orgs/{orgId}/work-orders
GET  /v1/orgs/{orgId}/work-orders/{id}
POST /v1/orgs/{orgId}/work-orders/{id}/lock
DELETE /v1/orgs/{orgId}/work-orders/{id}/lock

# Events & sync
POST /v1/orgs/{orgId}/events
POST /v1/orgs/{orgId}/sync/reconcile
```

All mutating routes require valid Firebase ID token and org membership. Lock routes additionally verify lock ownership.

### Plugin configuration

```typescript
// ui/src/lib/cloud-api.ts
export const LIVINGCOLOR_CLOUD_API_URL =
  import.meta.env.VITE_LC_CLOUD_API_URL ??
  'https://api-livingcolor.visualq.ai'
```

Optional dev override via env; production default is `api-livingcolor.visualq.ai`.

## Firestore security rules (principles)

- **Read:** authenticated user is member of `orgId` (custom claim or membership doc lookup).
- **Direct client write:** denied on `workOrders`, `locks`, `events` collections.
- **Writes:** only via Admin SDK on cloud API (bypasses rules).

## Plugin changes (high level)

| Area | Change |
| --- | --- |
| `FirebaseAuthGate` | Welcome screen; remove SA setup banner |
| `desktop-api.ts` | Team routes target cloud API base URL |
| `lc_server/api/firebase_routes.py` | Dev-only or deprecated for production |
| New `cloud-api.ts` + `sync/` module | Locks, pending events, reconcile |
| `workspace-scope` | Unchanged (`local` / `org:{id}`) |
| README | Personal default; team = sign-in only |

## Error handling

| Condition | Behavior |
| --- | --- |
| User chooses local | No cloud calls; no Firebase gate |
| Sign-in cancelled | Return to welcome screen |
| Cloud API 401/403 | Refresh Firebase token once; else sign out |
| Cloud API 503 | Offline banner; apply offline rules above |
| Lock denied | Toast: WO locked by another member |
| Reconcile conflict | Modal with diff; user chooses resolution path (v1: manual) |

## Security

- Service account JSON stored only in cloud platform secrets (`api-livingcolor.visualq.ai` deployment).
- Plugin repo contains only public Firebase web config.
- CORS on cloud API: allow Hermes dashboard origins (localhost + deployed dashboard URLs).
- Rate limiting on lock acquire and event append endpoints.

## Delivery phases

| Phase | Scope |
| --- | --- |
| **E1** | Welcome gate + personal-without-account; remove user SA docs |
| **E2** | Deploy `api-livingcolor.visualq.ai` — bootstrap, orgs, project config |
| **E3** | Firestore read listeners + WO lock API |
| **E4** | Event sync + offline `pending_events` + reconcile |
| **E5** | Share local → team + shared audit trail |

## Testing

- Plugin Vitest: welcome gate renders both paths; local path skips Firebase.
- Plugin Vitest: `callCloudApi` sends Bearer + org headers to `api-livingcolor.visualq.ai`.
- Cloud API integration tests: token verification, lock acquire/release, reconcile conflict.
- Manual: two browsers, same org — lock exclusivity and read-only for non-holder.

## Open questions (post-v1)

- WebSocket/SSE on `api-livingcolor.visualq.ai` for push sync (reduces polling).
- Firebase App Check on embedded web config.
- Enterprise self-hosted API override (`LIVINGCOLOR_CLOUD_API_URL`).
