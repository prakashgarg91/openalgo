import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { UniverseResult } from '@/api/algos'
import { UniversePanel, UniverseResultView } from './UniversePanel'

const api = vi.hoisted(() => ({ startUniverseSearch: vi.fn(), fetchBuilderJob: vi.fn() }))
vi.mock('@/api/algos', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/algos')>()),
  ...api,
}))

const s = (cagr: number, fall = -10000, worst = -3000) => ({
  cagr,
  total: 1000,
  max_drawdown: fall,
  worst_day: worst,
  days: 800,
})

function result(edge: boolean): UniverseResult {
  return {
    kind: 'universe',
    data_from: '2011-10-28',
    data_to: '2026-10-28',
    trials: 23,
    segments: {
      train: ['2012-11-02', '2019-11-07'],
      validate: ['2019-11-08', '2023-05-02'],
      test: ['2023-05-03', '2026-10-28'],
    },
    lost_to_cash_on_test: 11,
    baselines: {
      buy_and_hold: { train: s(9.4), validate: s(12.9), test: s(7.8) },
      cash: { train: s(5.2, 0, 24), validate: s(5.6, 0, 24), test: s(5.6, 0, 24) },
    },
    winner: {
      name: 'dual_momentum(lookback=126, mode=best)',
      stats: { train: s(7.7), validate: s(16.2), test: s(15.7, -25800, -10517) },
    },
    rules: [
      {
        name: 'dual_momentum(lookback=126, mode=best)',
        family: 'dual_momentum',
        train_cagr: 7.7,
        validate_cagr: 16.2,
        test_cagr: 15.7,
        test_excess_over_cash: 43866,
      },
      {
        name: 'seasonal(day=0, kind=weekday)',
        family: 'seasonal',
        train_cagr: -7,
        validate_cagr: 6,
        test_cagr: -6.3,
        test_excess_over_cash: -40443,
      },
    ],
    verdict: {
      edge_shown: edge,
      beats_cash: edge,
      beats_buy_and_hold: edge,
      lowers_risk_like_buy_and_hold: false,
      within_daily_cap: true,
      headline: edge
        ? 'It held up on data it was not chosen on. That is one test period, not proof.'
        : 'No edge shown over leaving the money in cash or buying and holding.',
      reasons: edge ? [] : ['It did not beat leaving the money in cash on both later periods.'],
    },
    account: {
      lots: 1,
      capital: 100000,
      max_daily_loss: 20000,
      final_equity: 164366,
      return_pct: 64.37,
      worst_day: -10517,
      max_drawdown: -25800,
      within_daily_cap: true,
      curve: [
        ['2023-05-03', 100000],
        ['2026-10-28', 164366],
      ],
    },
    caveats: [
      'Holding half Nifty and half gold is a fair comparison: most of any gain is owning equities and gold.',
    ],
  }
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

beforeEach(() => vi.clearAllMocks())

describe('UniversePanel', () => {
  it('shows the verdict, the baselines it must beat, and the account result', () => {
    wrap(<UniverseResultView result={result(true)} />)
    expect(screen.getByText(/held up on data it was not chosen on/)).toBeTruthy()
    expect(screen.getByText(/11 of them earned less than cash/)).toBeTruthy()
    expect(screen.getByText('Buy and hold the Nifty ETF, never seen')).toBeTruthy()
    expect(screen.getByText('Leave it in cash (6%), never seen')).toBeTruthy()
    expect(screen.getByText(/Rs 1,64,366/)).toBeTruthy()
    expect(screen.getByText(/No day passed your daily limit/)).toBeTruthy()
    expect(screen.getByText(/half Nifty and half gold/)).toBeTruthy()
  })

  it('says plainly when nothing beat cash or buy and hold', () => {
    wrap(<UniverseResultView result={result(false)} />)
    expect(screen.getByText(/No edge shown over leaving the money in cash/)).toBeTruthy()
    expect(screen.getByText(/did not beat leaving the money in cash/)).toBeTruthy()
  })

  it('starts the search with the typed account and shows what comes back', async () => {
    api.startUniverseSearch.mockResolvedValue('0123456789abcdef')
    api.fetchBuilderJob.mockResolvedValue({ state: 'done', result: result(true) })
    wrap(<UniversePanel />)
    fireEvent.change(screen.getByLabelText('Capital (Rs)'), { target: { value: '150000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search everything' }))
    expect(await screen.findByText(/Best found:/)).toBeTruthy()
    expect(api.startUniverseSearch).toHaveBeenCalledWith({ capital: 150000, max_daily_loss: 20000 })
  })

  it('shows the plain message when the search cannot start', async () => {
    api.startUniverseSearch.mockRejectedValue({
      response: { data: { message: 'A search is already running. It takes about a minute.' } },
    })
    wrap(<UniversePanel />)
    fireEvent.click(screen.getByRole('button', { name: 'Search everything' }))
    expect(await screen.findByText(/already running/)).toBeTruthy()
  })

  it('shows the download failure in words', async () => {
    api.startUniverseSearch.mockResolvedValue('0123456789abcdef')
    api.fetchBuilderJob.mockResolvedValue({
      state: 'failed',
      message:
        'Could not download market history. Check your internet connection and try again in a minute.',
    })
    wrap(<UniversePanel />)
    fireEvent.click(screen.getByRole('button', { name: 'Search everything' }))
    expect(await screen.findByText(/Could not download market history/)).toBeTruthy()
  })
})
