import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AlgoItem } from '@/api/algos'
import { ChooserPanel } from './ChooserPanel'
import { DebuggerPanel } from './DebuggerPanel'

const api = vi.hoisted(() => ({
  fetchChooserToday: vi.fn(),
  rebuildChooser: vi.fn(),
  fetchBuilderJob: vi.fn(),
  debugDay: vi.fn(),
  fetchExplanations: vi.fn(),
}))
vi.mock('@/api/algos', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/algos')>()),
  ...api,
}))

const cell = (trades: number, total: number) => ({ trades, total, avg: 0, profit_factor: 1 })

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

beforeEach(() => vi.clearAllMocks())

describe('ChooserPanel', () => {
  it('stands aside and says, algo by algo, why', async () => {
    api.fetchChooserToday.mockResolvedValue({
      regime: {},
      decision: {
        pick: null,
        headline: 'Standing aside: no algo has earned a place on a calm day.',
        candidates: [
          {
            algo_id: 'zen',
            name: 'Zen',
            eligible: false,
            reasons: ['good in the older years but lost money in the newer years'],
            evidence: cell(352, 37652),
            check: cell(113, -46241),
          },
        ],
      },
      table: {
        built_at: '2026-10-28',
        first: '2016-12-05',
        split: '2024-09-16',
        last: '2026-10-22',
      },
    })
    wrap(<ChooserPanel />)
    expect(await screen.findByText(/Standing aside: no algo has earned/)).toBeTruthy()
    expect(screen.getByText('Does not qualify')).toBeTruthy()
    expect(screen.getByText(/lost money in the newer years/)).toBeTruthy()
    expect(screen.getByText(/not real fills/)).toBeTruthy()
  })

  it('refreshes the evidence in the background and reloads when it is done', async () => {
    api.fetchChooserToday.mockResolvedValue({
      regime: {},
      decision: {
        pick: null,
        headline: 'Standing aside: the evidence table has not been built yet.',
        candidates: [],
      },
      table: null,
    })
    api.rebuildChooser.mockResolvedValue('0123456789abcdef')
    api.fetchBuilderJob.mockResolvedValue({ state: 'done', result: {} })
    wrap(<ChooserPanel />)
    fireEvent.click(await screen.findByRole('button', { name: /Refresh the evidence/ }))
    await waitFor(() => expect(api.fetchChooserToday.mock.calls.length).toBeGreaterThan(1))
  })
})

describe('DebuggerPanel', () => {
  const algos = [
    { id: 'zen', name: 'Zen' },
    { id: 'smart_pick', name: 'Smart Pick' },
  ] as AlgoItem[]

  it('explains a day step by step and marks where it stopped', async () => {
    api.debugDay.mockResolvedValue({
      algo_name: 'Zen',
      verdict: 'Zen sat out 2024-03-14: Does Zen trade this kind of day.',
      steps: [
        { title: 'What kind of day it was', status: 'info', detail: 'Volatile day.' },
        {
          title: 'Does Zen trade this kind of day?',
          status: 'stop',
          detail: 'It trades calm days.',
        },
      ],
    })
    wrap(<DebuggerPanel algos={algos} />)
    expect(screen.queryByRole('option', { name: 'Smart Pick' })).toBeNull()
    fireEvent.change(screen.getByLabelText('Day'), { target: { value: '2024-03-14' } })
    fireEvent.click(screen.getByRole('button', { name: 'Explain that day' }))
    expect(await screen.findByText(/Zen sat out 2024-03-14/)).toBeTruthy()
    expect(screen.getByText(/Stopped here/)).toBeTruthy()
    expect(api.debugDay).toHaveBeenCalledWith('zen', '2024-03-14')
  })

  it('shows the plain message when a day cannot be replayed', async () => {
    api.debugDay.mockRejectedValue({
      response: { data: { message: 'That day cannot be replayed.' } },
    })
    wrap(<DebuggerPanel algos={algos} />)
    fireEvent.change(screen.getByLabelText('Day'), { target: { value: '2024-01-06' } })
    fireEvent.click(screen.getByRole('button', { name: 'Explain that day' }))
    expect(await screen.findByText('That day cannot be replayed.')).toBeTruthy()
  })
})
