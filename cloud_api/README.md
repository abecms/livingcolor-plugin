# LivingColor Cloud API

FastAPI service for **Team** mode (`livingcolor-app` Firebase project). Production is hosted on VisualQ at `https://api-livingcolor.visualq.ai/v1/*`; this package is the reference implementation and local dev entrypoint.

## Run locally

```bash
export FIREBASE_PROJECT_ID=livingcolor-app
export FIREBASE_CLIENT_EMAIL=...
export FIREBASE_PRIVATE_KEY=...
# or: export FIREBASE_SERVICE_ACCOUNT_PATH=~/.livingcolor/firebase-service-account.json

uvicorn cloud_api.main:app --reload --port 8080
curl http://127.0.0.1:8080/v1/health
```

Plugin dev override: `VITE_LC_CLOUD_API_URL=http://127.0.0.1:8080`

## Deploy (optional standalone)

See `../visualq/services/livingcolor-api/` for Fly.io / Cloud Run scripts. Production uses the VisualQ Next.js `/v1` routes.

## Firestore security rules

Client-side Firestore access is **read-only** for org members. All writes go through the cloud API (Admin SDK).

Deploy rules to the `livingcolor-app` project:

```bash
# From livingcolor-plugin root (requires Firebase CLI + livingcolor-app project)
firebase deploy --only firestore:rules --project livingcolor-app
```

Rules file: [`../firestore.rules`](../firestore.rules)

## API routes (v1)

| Area | Paths |
|------|--------|
| Health | `GET /v1/health` |
| Session | `GET /v1/config/firebase-client`, `POST /v1/session/bootstrap`, `GET /v1/me` |
| Orgs | `GET/POST /v1/orgs`, members, invites, preferences |
| Projects | CRUD under `/v1/orgs/{orgId}/projects/...` |
| Locks | `POST/DELETE /v1/orgs/{orgId}/work-orders/{woId}/lock` |
| Events | `POST /v1/orgs/{orgId}/events` |
| Sync | `POST /v1/orgs/{orgId}/sync/reconcile` |
