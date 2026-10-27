/**
 * What this pins.
 *
 * The page is the only thing between a trader and a Live switch, so the tests
 * are about that: a stopped algo reads Stopped and Sandbox, Go Live stays off
 * until the record allows it, and the confirmation needs the worst-case loss
 * typed back before anything is sent. The words are the trader's own
 * (Active, Stopped, Sandbox, Live), never a machine term.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AlgoItem, Deployment } from '@/api/algos'
import Algos from './Algos'

const api = vi.hoisted(() => ({
  fetchCatalogue: vi.fn(),
  fetchRegime: vi.fn(),
  fetchCoverage: vi.fn(),
  previewAlgo: vi.fn(),
  deployAlgo: vi.fn(),
  setAlgoActive: vi.fn(),
  setAlgoLive: vi.fn(),
  checkAlgoNow: vi.fn(),
  removeAlgo: vi.fn(),
  fetchReadiness: vi.fn(),
}))

vi.mock('@/api/algos', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/algos')>()),
  ...api,
}))

const record = { runs: 12, wins: 8, net_pnl: 4200, worst_run: -900, available: true }

function deployment(overrides: Partial<Deployment> = {}): Deployment {
  return {
    id: 1,
    algo_id: 'zen',
    strategy_id: 5,
    capital: 500000,
    active: false,
    mode: 'sandbox',
    live_enabled: false,
    position_open: false,
    max_loss_ceiling_inr: 45000,
    recent_decisions: [],
    live_gate: { allowed: true, needed_runs: 10, reason: '', record },
    ...overrides,
  }
}

function algo(deployed: Deployment | null): AlgoItem {
  return {
    id: 'zen',
    name: 'Zen',
    summary: 'Overnight hedged credit spread.',
    risk: 'medium',
    allowed_regimes: ['calm', 'trending'],
    overnight: true,
    entry_time: '15:05',
    status: 'tested',
    evidence: 'Indicative test on Nifty data.',
    deployment: deployed,
  }
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Algos />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.fetchRegime.mockResolvedValue({
    label: 'calm',
    bias: 'neutral',
    score: 0,
    confidence: 0.9,
    reasons: ['No large gap'],
    missing: [],
    missing_labels: [],
    reliable: true,
  })
  api.fetchReadiness.mockResolvedValue({
    ready_for_sandbox: true,
    ready_for_live: false,
    next: 'broker',
    steps: [
      { id: 'api_key', label: 'OpenAlgo API key', state: 'done', detail: 'Created.', path: null },
      {
        id: 'broker',
        label: 'Upstox login for today',
        state: 'todo',
        detail: 'Log in to your broker again. Broker logins expire every morning.',
        path: '/broker',
      },
    ],
  })
  api.fetchCoverage.mockResolvedValue({
    regimes: { calm: ['zen'], trending: ['zen'], volatile: [], event: [] },
    stands_aside_on: ['volatile', 'event'],
  })
})

describe('Algos page', () => {
  it('tells the trader what blocks Live and links to the fix', async () => {
    api.fetchCatalogue.mockResolvedValue([algo(null)])
    renderPage()
    expect(await screen.findByText('Before you can go Live')).toBeTruthy()
    expect(screen.getByText('Upstox login for today')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open' }).getAttribute('href')).toBe('/broker')
  })

  it('shows the regime and the days the platform stands aside', async () => {
    api.fetchCatalogue.mockResolvedValue([algo(null)])
    renderPage()
    expect(await screen.findByText('No large gap')).toBeTruthy()
    expect(screen.getAllByText('Calm').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Stands aside')).toHaveLength(2)
    expect(await screen.findByRole('button', { name: /Add in Sandbox mode/ })).toBeTruthy()
  })

  it('reads a new algo as Stopped and Sandbox', async () => {
    api.fetchCatalogue.mockResolvedValue([algo(deployment())])
    renderPage()
    expect(await screen.findByText('Stopped')).toBeTruthy()
    expect(screen.getByText('Sandbox')).toBeTruthy()
  })

  it('keeps Go Live off and says why until the Sandbox record allows it', async () => {
    api.fetchCatalogue.mockResolvedValue([
      algo(
        deployment({
          live_gate: {
            allowed: false,
            needed_runs: 10,
            reason: 'Run this algo in Sandbox for 10 trades first. It has completed 2 so far.',
            record: { ...record, runs: 2 },
          },
        })
      ),
    ])
    renderPage()
    const button = await screen.findByRole('button', { name: /Go Live/ })
    expect((button as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/10 trades first/)).toBeTruthy()
  })

  it('sends nothing until the worst-case loss is typed back', async () => {
    api.fetchCatalogue.mockResolvedValue([algo(deployment())])
    api.setAlgoLive.mockResolvedValue(deployment({ mode: 'live' }))
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /^Go Live$/ }))
    const confirm = screen.getAllByRole('button', { name: /^Go Live$/ }).at(-1) as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    expect(api.setAlgoLive).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Worst-case loss in rupees'), {
      target: { value: '45000' },
    })
    fireEvent.click(confirm)
    await waitFor(() => expect(api.setAlgoLive).toHaveBeenCalledWith(1, true, 45000))
  })

  it('marks an experimental algo and shows its evidence', async () => {
    api.fetchCatalogue.mockResolvedValue([
      { ...algo(null), status: 'experimental', evidence: 'Lost money in the test.' },
    ])
    renderPage()
    expect(await screen.findByText('Experimental')).toBeTruthy()
    expect(screen.getByText('Lost money in the test.')).toBeTruthy()
  })

  it('warns about the next-morning exit for an overnight algo', async () => {
    api.fetchCatalogue.mockResolvedValue([algo(deployment())])
    renderPage()
    expect(await screen.findByText(/exits at 09:45 the next morning/)).toBeTruthy()
  })

  it('refuses to name the market when too little data is available, in words a trader reads', async () => {
    api.fetchRegime.mockResolvedValue({
      label: 'trending',
      bias: 'bullish',
      score: 0.4,
      confidence: 0.42,
      reasons: ['Cues point up'],
      missing: ['vix', 'gap_pct'],
      missing_labels: ['India VIX', "today's Nifty move"],
      reliable: false,
    })
    api.fetchCatalogue.mockResolvedValue([algo(null)])
    renderPage()
    expect(await screen.findByText('Not enough data')).toBeTruthy()
    expect(screen.getByText(/stand aside until there is more/)).toBeTruthy()
    expect(screen.getByText(/No data for: India VIX, today's Nifty move/)).toBeTruthy()
    expect(screen.queryByText(/Bullish lean/i)).toBeNull()
    expect(screen.queryByText('Cues point up')).toBeNull()
    expect(document.body.textContent).not.toMatch(/gap_pct|vix_change|nifty_vs_ma20/)
  })

  it('shows algo names, not ids, in the coverage row', async () => {
    api.fetchCoverage.mockResolvedValue({
      regimes: { calm: ['calm_condor'], trending: ['mirror_zen'], volatile: [], event: [] },
      stands_aside_on: ['volatile', 'event'],
    })
    api.fetchCatalogue.mockResolvedValue([
      { ...algo(null), id: 'calm_condor', name: 'Calm Condor' },
      { ...algo(null), id: 'mirror_zen', name: 'Mirror Zen' },
    ])
    renderPage()
    expect(await screen.findByText('No large gap')).toBeTruthy()
    expect(await screen.findAllByText(/Calm Condor/)).not.toHaveLength(0)
    expect(document.body.textContent).not.toMatch(/calm_condor|mirror_zen/)
  })

  it("shows the algo's own check time, not a fixed one", async () => {
    api.fetchCatalogue.mockResolvedValue([
      { ...algo(deployment()), entry_time: '09:25', overnight: false },
    ])
    renderPage()
    expect(await screen.findByText(/Checks the market at 09:25/)).toBeTruthy()
    expect(screen.getByText(/The first check runs at 09:25/)).toBeTruthy()
  })

  it('does not warn about an overnight exit on an intraday algo', async () => {
    api.fetchCatalogue.mockResolvedValue([{ ...algo(deployment()), overnight: false }])
    renderPage()
    expect(await screen.findByText(/trades within the day/)).toBeTruthy()
    expect(screen.queryByText(/exits at 09:45 the next morning/)).toBeNull()
  })

  it('never uses the word armed anywhere a trader reads', async () => {
    api.fetchCatalogue.mockResolvedValue([algo(deployment())])
    const { container } = renderPage()
    await screen.findByText('Stopped')
    expect(container.textContent?.toLowerCase()).not.toMatch(/\barm(ed|ing)?\b/)
  })
})
