import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearProjectChatSessionId,
  extractProjectChatSessionId,
  getProjectChatSessionId,
  isProjectChatSessionTitle,
  projectChatSessionTitle,
  setProjectChatSessionId
} from './project-chat-session'

const STORAGE_KEY = 'livingcolor.projectChatSessions'

describe('project-chat-session', () => {
  beforeEach(() => {
    window.localStorage.removeItem(STORAGE_KEY)
  })

  it('round-trips session ids per project key', () => {
    setProjectChatSessionId('bn', 'session-abc')
    expect(getProjectChatSessionId('BN')).toBe('session-abc')
  })

  it('clears only the requested project', () => {
    setProjectChatSessionId('BN', 'session-bn')
    setProjectChatSessionId('TVP', 'session-tvp')

    clearProjectChatSessionId('bn')

    expect(getProjectChatSessionId('BN')).toBeNull()
    expect(getProjectChatSessionId('TVP')).toBe('session-tvp')
  })

  it('builds a stable session title', () => {
    expect(projectChatSessionTitle('bn')).toBe('LivingColor BN')
  })

  it('matches project chat session titles case-insensitively', () => {
    expect(isProjectChatSessionTitle('LivingColor BN', 'bn')).toBe(true)
    expect(isProjectChatSessionTitle('Cron BN tickets', 'bn')).toBe(false)
  })

  it('extracts the Hermes session id from terminal output', () => {
    expect(extractProjectChatSessionId('Session: a02ac969')).toBe('a02ac969')
    expect(extractProjectChatSessionId('\x1b[90mSession: abc12345\x1b[0m')).toBe('abc12345')
  })
})
