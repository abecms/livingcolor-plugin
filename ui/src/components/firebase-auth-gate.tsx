import type { ReactNode } from 'react'

import { FirebaseLoginPage } from '@/app/auth/firebase-login-page'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'

function FirebaseSetupBanner() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center bg-background px-6 py-12">
      <div className="w-full max-w-lg space-y-4 rounded-xl border border-border bg-card p-8 shadow-sm">
        <h1 className="text-xl font-semibold tracking-tight">Firebase team workspaces</h1>
        <p className="text-sm text-muted-foreground">
          Team collaboration requires Firebase Admin credentials on the machine running the Hermes
          dashboard. Add a service account JSON and restart the dashboard.
        </p>
        <pre className="overflow-x-auto rounded-md bg-muted px-3 py-2 text-xs">
          {`# ~/.hermes/livingcolor/.env
FIREBASE_SERVICE_ACCOUNT_PATH=~/.hermes/livingcolor/firebase-sa.json`}
        </pre>
        <p className="text-sm text-muted-foreground">
          See the plugin README for download steps from the Firebase console (<code>livingcolor-app</code>{' '}
          project).
        </p>
      </div>
    </div>
  )
}

export function FirebaseAuthGate({ children }: { children: ReactNode }) {
  const { enabled, status } = useFirebaseAuth()

  if (status === 'disabled') {
    return <FirebaseSetupBanner />
  }

  if (!enabled) {
    return children
  }

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Signing in…</p>
      </div>
    )
  }

  if (status === 'signed-out') {
    return <FirebaseLoginPage />
  }

  return children
}
