import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { IdeaTracker } from '@/api/algos'
import { AutoBuilderPanel } from './AutoBuilderPanel'

const tracker: IdeaTracker = {
  trial_count: 325,
  pass_bar: 0.025 / 325,
  standard_errors_needed: 3.8,
  next_free_month: '2027-01',
  ideas: [
    {
      id: 'a',
      name: 'Idea A',
      registered: '2027-01-04',
      slot: '2027-01',
      trial_numbers: [321, 321],
      stage: 'Rejected by its own tests',
      failed_gates: ['beats the hold'],
      why_it_might_work: 'w',
      how_it_fails: 'f',
      intact: true,
    },
  ],
  stage_counts: {},
  lessons: [{ gate: 'beats the hold', ideas_missed: 1 }],
  forward_tests: [],
  live_gate: 'locked',
  rules: ['One new idea a month.'],
}

vi.mock('@/api/algos', async (original) => ({
  ...(await original<typeof import('@/api/algos')>()),
  fetchIdeaTracker: vi.fn(async () => tracker),
}))

describe('AutoBuilderPanel', () => {
  it('shows the real counts, the failed gate and a locked live gate, with no action buttons', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AutoBuilderPanel />
      </QueryClientProvider>
    )
    expect(await screen.findByText('Idea A')).toBeTruthy()
    expect(screen.getByText('325')).toBeTruthy()
    expect(screen.getByText(/Missed: beats the hold/)).toBeTruthy()
    expect(screen.getByText('Live gate: locked.')).toBeTruthy()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })
})
