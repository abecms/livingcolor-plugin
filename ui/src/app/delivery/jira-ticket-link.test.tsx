import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { JiraTicketTitleLink } from './jira-ticket-link'

vi.mock('./jira-browse-context', () => ({
  useJiraBrowseBaseUrl: () => 'https://jira.example.com/'
}))

const openExternalLink = vi.fn()

vi.mock('@/lib/external-link', () => ({
  openExternalLink: (...args: unknown[]) => openExternalLink(...args)
}))

afterEach(() => {
  cleanup()
  openExternalLink.mockClear()
})

describe('JiraTicketTitleLink', () => {
  it('opens the Jira browse URL when the title is clicked', () => {
    render(
      <JiraTicketTitleLink jiraKey="BN-441">
        Audio player insight bug
      </JiraTicketTitleLink>
    )

    fireEvent.click(screen.getByRole('button', { name: /Audio player insight bug/i }))

    expect(openExternalLink).toHaveBeenCalledWith('https://jira.example.com/browse/BN-441')
  })
})
