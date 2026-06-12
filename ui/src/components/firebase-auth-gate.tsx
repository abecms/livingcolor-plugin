import { useState, type ReactNode } from 'react'

import { FirebaseLoginPage } from '@/app/auth/firebase-login-page'
import { WelcomePage } from '@/app/auth/welcome-page'
import { LivingColorChromeLayout } from '@/components/livingcolor-chrome-layout'
import { LivingColorLogo } from '@/components/livingcolor-logo'
import { useFirebaseAuth } from '@/hooks/use-firebase-auth'
import { readStoredWorkspaceScope, switchToLocalWorkspace } from '@/store/workspace-scope'

export function FirebaseAuthGate({ children }: { children: ReactNode }) {
  const { enabled, status } = useFirebaseAuth()
  const [showLogin, setShowLogin] = useState(false)
  const [localChosen, setLocalChosen] = useState(
    () => readStoredWorkspaceScope()?.mode === 'local'
  )

  if (!enabled || status === 'signed-in') {
    return children
  }

  if (status === 'loading') {
    return (
      <LivingColorChromeLayout>
        <div className="flex h-full flex-col items-center justify-center gap-6">
          <LivingColorLogo height={32} />
          <p className="text-sm text-muted-foreground">Signing in…</p>
        </div>
      </LivingColorChromeLayout>
    )
  }

  if (status === 'signed-out') {
    if (localChosen) {
      return children
    }

    if (showLogin) {
      return (
        <LivingColorChromeLayout>
          <FirebaseLoginPage />
        </LivingColorChromeLayout>
      )
    }

    return (
      <LivingColorChromeLayout>
        <WelcomePage
          onContinueLocal={() => {
            switchToLocalWorkspace()
            setLocalChosen(true)
            setShowLogin(false)
          }}
          onSignIn={() => setShowLogin(true)}
        />
      </LivingColorChromeLayout>
    )
  }

  return children
}
