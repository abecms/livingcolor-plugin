import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FirebaseAuthGate } from './firebase-auth-gate'

const mockUseFirebaseAuth = vi.fn()

vi.mock('@/hooks/use-firebase-auth', () => ({
  useFirebaseAuth: () => mockUseFirebaseAuth()
}))

vi.mock('@/app/auth/firebase-login-page', () => ({
  FirebaseLoginPage: () => <div>Login page</div>
}))

vi.mock('@/store/workspace-scope', () => ({
  readStoredWorkspaceScope: vi.fn(() => null),
  switchToLocalWorkspace: vi.fn()
}))

import { readStoredWorkspaceScope, switchToLocalWorkspace } from '@/store/workspace-scope'

describe('FirebaseAuthGate', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.mocked(readStoredWorkspaceScope).mockReturnValue(null)
    mockUseFirebaseAuth.mockReturnValue({ enabled: true, status: 'signed-out' })
  })

  it('shows welcome choices when signed out without a stored local scope', () => {
    render(
      <FirebaseAuthGate>
        <div>App</div>
      </FirebaseAuthGate>
    )
    expect(screen.getByText('Continue locally')).toBeTruthy()
    expect(screen.getByText('Sign in to collaborate')).toBeTruthy()
  })

  it('shows login when user chooses sign in', () => {
    render(
      <FirebaseAuthGate>
        <div>App</div>
      </FirebaseAuthGate>
    )
    fireEvent.click(screen.getByText('Sign in to collaborate'))
    expect(screen.getByText('Login page')).toBeTruthy()
  })

  it('passes through to app when user continues locally', () => {
    render(
      <FirebaseAuthGate>
        <div>App</div>
      </FirebaseAuthGate>
    )
    fireEvent.click(screen.getByText('Continue locally'))
    expect(switchToLocalWorkspace).toHaveBeenCalled()
    expect(screen.getByText('App')).toBeTruthy()
  })

  it('passes through when stored scope is already local', () => {
    vi.mocked(readStoredWorkspaceScope).mockReturnValue({ mode: 'local' })
    render(
      <FirebaseAuthGate>
        <div>App</div>
      </FirebaseAuthGate>
    )
    expect(screen.getByText('App')).toBeTruthy()
  })

})
