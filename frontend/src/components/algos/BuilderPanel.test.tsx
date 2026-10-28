import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BuilderResult, BuilderStats } from '@/api/algos'
import { BuilderPanel, BuilderResultView, BuiltAlgoTools } from './BuilderPanel'

const api = vi.hoisted(() => ({
  startBuilderSearch: vi.fn(),
  fetchBuilderJob: vi.fn(),
  saveBuiltAlgo: vi.fn(),
  deleteBuiltAlgo: vi.fn(),
  fetchProposal: vi.fn(),
}))

vi.mock('@/api/algos', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/algos')>()),
  ...api,
}))

const stats = (total: number, pf: number | null = 1.1): BuilderStats => ({
  trades: 100,
  win_rate: 60,
  avg: total / 100,
  total,
  max_drawdown: -900,
  profit_factor: pf,
})

function result(edge: boolean): BuilderResult {
  return {
    trials: 40,
    lost_on_test: 38,
    segments: {
      train: ['2016-12-05', '2021-11-13'],
      validate: ['2021-11-13', '2024-05-03'],
      test: ['2024-05-03', '2026-10-22'],
    },
    baseline_test: stats(-54721, 0.06),
    winner: {
      spec: {},
      name: 'Bull put OTM2/OTM5 on calm days, skipping expiry eve',
      train: stats(61212, 1.9),
      validate: stats(18549, 1.26),
      test: stats(edge ? 9000 : -84946, edge ? 1.5 : 0.45),
    },
    shortlist: [],
    verdict: edge
      ? { edge_shown: true, headline: 'It held up on data it was not chosen on.', reasons: [] }
      : {
          edge_shown: false,
          headline:
            'No edge shown. The best configuration found did not survive data it was not chosen on.',
          reasons: ['It lost money on the period nothing was chosen on.'],
        },
    caveats: ['Even the conservative model is not real option prices.'],
  }
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

beforeEach(() => vi.clearAllMocks())

describe('Builder', () => {
  it('says plainly when nothing held up, and shows the period nothing was chosen on', () => {
    wrap(<BuilderResultView jobId="j" result={result(false)} />)
    expect(screen.getByText(/No edge shown/)).toBeTruthy()
    expect(screen.getByText(/38 of them lost money/)).toBeTruthy()
    expect(screen.getByText(/Never seen: 2024-05-03 to 2026-10-22/)).toBeTruthy()
    expect(screen.getByText(/only a candidate/)).toBeTruthy()
  })

  it('does not say profit when an edge is shown; it says one test period is not proof', () => {
    wrap(<BuilderResultView jobId="j" result={result(true)} />)
    expect(screen.getByText(/held up on data it was not chosen on/)).toBeTruthy()
    expect(screen.queryByText(/profitable/i)).toBeNull()
  })

  it('saves under the name the trader typed', async () => {
    api.saveBuiltAlgo.mockResolvedValue({ algo_id: 'custom_1' })
    wrap(<BuilderResultView jobId="job-1" result={result(false)} />)
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'My put' } })
    fireEvent.click(screen.getByRole('button', { name: /Save to my algos/ }))
    await waitFor(() => expect(api.saveBuiltAlgo).toHaveBeenCalledWith('job-1', 'My put'))
  })

  it('starts a search with the chosen options and shows the result when done', async () => {
    api.startBuilderSearch.mockResolvedValue('job-9')
    api.fetchBuilderJob.mockResolvedValue({ state: 'done', result: result(false) })
    wrap(<BuilderPanel />)
    fireEvent.click(screen.getByLabelText('Bear call spread'))
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText(/No edge shown/)).toBeTruthy()
    expect(api.startBuilderSearch).toHaveBeenCalledWith({
      families: ['condor', 'bull_put', 'bear_call'],
      label_sets: [['calm'], ['calm', 'trending']],
    })
  })

  it('shows the server message when a search cannot start', async () => {
    api.startBuilderSearch.mockRejectedValue({
      response: { data: { message: 'A search is already running. It takes about a minute.' } },
    })
    wrap(<BuilderPanel />)
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText(/already running/)).toBeTruthy()
  })
})

describe('BuiltAlgoTools weekly check', () => {
  it('shows a waiting proposal and says nothing was changed', async () => {
    api.fetchProposal.mockResolvedValue({
      checked_on: '2026-10-25',
      verdict: 'v',
      trials: 60,
      proposal: { name: 'Bull put OTM2/OTM5', why: 'It made more on the latest period.' },
    })
    wrap(<BuiltAlgoTools customId={3} deployed={false} />)
    expect(await screen.findByText(/found a setup that looks better/)).toBeTruthy()
    expect(screen.getByText(/Nothing was changed/)).toBeTruthy()
  })

  it('says when the weekly check recommends no change', async () => {
    api.fetchProposal.mockResolvedValue({
      checked_on: '2026-10-25',
      verdict: 'v',
      trials: 60,
      proposal: null,
    })
    wrap(<BuiltAlgoTools customId={3} deployed={false} />)
    expect(await screen.findByText(/no change recommended/)).toBeTruthy()
  })

  it('stays quiet before the first weekly check', async () => {
    api.fetchProposal.mockResolvedValue(null)
    wrap(<BuiltAlgoTools customId={3} deployed={false} />)
    await screen.findByRole('button', { name: 'Check for a better version' })
    expect(screen.queryByText(/weekly check/i)).toBeNull()
  })
})
