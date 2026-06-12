import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SprintHeaderStrip } from './sprint-header-strip'

afterEach(() => {
  cleanup()
})

const sprint = {
  sprintName: 'Sprint 14',
  capacityDays: 10,
  usedDays: 6,
  durationDays: 14,
  overflowRisk: false,
  warnings: [],
  tickets: []
}

describe('SprintHeaderStrip', () => {
  it('shows sprint name and capacity', () => {
    render(
      <SprintHeaderStrip
        analysisRunning={false}
        clarificationCount={0}
        onOpenClarifications={() => {}}
        onRunAnalysis={() => {}}
        sprint={sprint}
      />
    )
    expect(screen.getByText('Sprint 14')).toBeTruthy()
    expect(screen.getByText(/6.*10/)).toBeTruthy()
  })

  it('shows the clarification chip only when count > 0 and forwards clicks', () => {
    const onOpen = vi.fn()
    const { rerender } = render(
      <SprintHeaderStrip
        analysisRunning={false}
        clarificationCount={0}
        onOpenClarifications={onOpen}
        onRunAnalysis={() => {}}
        sprint={sprint}
      />
    )
    expect(screen.queryByRole('button', { name: /clarif/i })).toBeNull()

    rerender(
      <SprintHeaderStrip
        analysisRunning={false}
        clarificationCount={2}
        onOpenClarifications={onOpen}
        onRunAnalysis={() => {}}
        sprint={sprint}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /2 to clarify/i }))
    expect(onOpen).toHaveBeenCalledOnce()
  })

  it('disables the analysis button while running', () => {
    render(
      <SprintHeaderStrip
        analysisRunning
        clarificationCount={0}
        onOpenClarifications={() => {}}
        onRunAnalysis={() => {}}
        sprint={sprint}
      />
    )
    const button = screen.getByRole('button', { name: /running/i }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
  })

  it('renders a fallback when no sprint is selected', () => {
    render(
      <SprintHeaderStrip
        analysisRunning={false}
        clarificationCount={0}
        onOpenClarifications={() => {}}
        onRunAnalysis={() => {}}
        sprint={null}
      />
    )
    expect(screen.getByText(/no sprint/i)).toBeTruthy()
  })
})
