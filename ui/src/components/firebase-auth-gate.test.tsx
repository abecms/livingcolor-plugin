import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { FirebaseAuthGate } from './firebase-auth-gate'

vi.mock('@/hooks/use-firebase-auth', () => ({
  useFirebaseAuth: () => ({ enabled: true, status: 'signed-out' })
}))

vi.mock('@/app/auth/firebase-login-page', () => ({
  FirebaseLoginPage: () => <div>Login page</div>
}))

describe('FirebaseAuthGate', () => {
  it('shows login when signed out and firebase enabled', () => {
    render(
      <FirebaseAuthGate>
        <div>App</div>
      </FirebaseAuthGate>
    )
    expect(screen.getByText('Login page')).toBeTruthy()
  })
})
