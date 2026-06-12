import { useState } from 'react'

import { cn } from '@/lib/utils'
import {
  registerWithEmail,
  signInWithEmail,
  signInWithGoogle
} from '@/services/firebase'

type Mode = 'sign-in' | 'register'

export function FirebaseLoginPage() {
  const [mode, setMode] = useState<Mode>('sign-in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  async function submitEmail(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      if (mode === 'register') {
        await registerWithEmail(email.trim(), password)
        setInfo('Check your inbox to verify your email, then sign in.')
        setMode('sign-in')
      } else {
        await signInWithEmail(email.trim(), password)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setBusy(false)
    }
  }

  async function submitGoogle() {
    setBusy(true)
    setError(null)
    setInfo('Opening Google sign-in…')
    try {
      await signInWithGoogle()
    } catch (err) {
      setInfo(null)
      setError(err instanceof Error ? err.message : 'Google sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 shadow-sm">
        <div className="mb-8 space-y-2 text-center">
          <p className="text-sm text-muted-foreground">Sign in to sync project settings across devices.</p>
        </div>

        <form className="space-y-4" onSubmit={submitEmail}>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Email</span>
            <input
              autoComplete="email"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              disabled={busy}
              onChange={event => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Password</span>
            <input
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              disabled={busy}
              minLength={6}
              onChange={event => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          {info ? <p className="text-sm text-muted-foreground">{info}</p> : null}

          <button
            className={cn(
              'w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
              busy && 'opacity-60'
            )}
            disabled={busy}
            type="submit"
          >
            {mode === 'register' ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <div className="my-6 flex items-center gap-3">
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs uppercase tracking-wide text-muted-foreground">or</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <button
          className={cn(
            'w-full rounded-md border border-input px-4 py-2 text-sm font-medium',
            busy && 'opacity-60'
          )}
          disabled={busy}
          onClick={() => void submitGoogle()}
          type="button"
        >
          Continue with Google
        </button>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          {mode === 'sign-in' ? (
            <>
              No account yet?{' '}
              <button
                className="font-medium text-foreground underline-offset-4 hover:underline"
                disabled={busy}
                onClick={() => setMode('register')}
                type="button"
              >
                Register
              </button>
            </>
          ) : (
            <>
              Already registered?{' '}
              <button
                className="font-medium text-foreground underline-offset-4 hover:underline"
                disabled={busy}
                onClick={() => setMode('sign-in')}
                type="button"
              >
                Sign in
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  )
}
