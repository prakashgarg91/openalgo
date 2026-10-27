/**
 * What this pins.
 *
 * The Lab is where a trader decides whether to trust an algo, and it showed
 * misleading profits before the pricing was checked against real option prices.
 * So these tests are about honesty: the cautious model is the default, the simple
 * one is labelled as flattering, and the caveats are on screen beside every
 * result. A failure reads as a sentence, never as a code.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AlgoItem, LabResult } from '@/api/algos'
import { LabPanel } from './LabPanel'

const api = vi.hoisted(() => ({ runLab: vi.fn() }))
vi.mock('@/api/algos', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/algos')>()),
  ...api,
}))

function algo(id: string, name: string): AlgoItem {
  return {
    id,
    name,
    summary: '',
    risk: 'medium',
    allowed_regimes: ['calm'],
    overnight: true,
    entry_time: '15:05',
    status: 'experimental',
    evidence: '',
    deployment: null,
  }
}

const ALGOS = [algo('zen', 'Zen'), algo('calm_condor', 'Calm Condor')]

const metrics = {
  trades: 120,
  win_rate: 41.5,
  avg: -243,
  total: -29160,
  max_drawdown: -50000,
  profit_factor: 0.54,
  worst: -9000,
  best: 800,
  avg_cost: 257,
  avg_gross: 14,
  break_even_cost: 14,
}

const RESULT: LabResult = {
  algo_id: 'zen',
  algo_name: 'Zen',
  model: { name: 'conservative', label: 'Conservative (variance clock, skew, itemised costs)' },
  gated: true,
  start: '2023-01-02',
  end: '2026-10-23',
  days: 940,
  metrics,
  yearly: [
    { year: 2023, ...metrics, trades: 40, total: -3500 },
    { year: 2024, ...metrics, trades: 80, total: -25660 },
  ],
  curve: [
    ['2023-01-03', -100],
    ['2023-06-01', -900],
    ['2024-12-31', -29160],
  ],
  trades: [],
  skipped: [{ reason: 'Zen does not trade a volatile market', days: 103 }],
  notes: [],
  caveats: [
    'This is a replay on daily prices with modelled option prices, not real fills. Real results will differ.',
    'Stops and targets are not simulated. Each trade is held until its exit time.',
  ],
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <LabPanel algos={ALGOS} />
    </QueryClientProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('LabPanel', () => {
  it('defaults to the cautious model and the market check, and labels the simple model as flattering', async () => {
    api.runLab.mockResolvedValue(RESULT)
    renderPanel()
    expect(screen.getByRole('option', { name: /Simple \(flatters option sellers\)/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Run the replay/ }))
    await waitFor(() =>
      expect(api.runLab).toHaveBeenCalledWith({
        algo_id: 'zen',
        model: 'conservative',
        gated: true,
        start: undefined,
      })
    )
  })

  it('sends the algo, period, model and market-check choices the trader made', async () => {
    api.runLab.mockResolvedValue(RESULT)
    renderPanel()
    fireEvent.change(screen.getByLabelText('Algo'), { target: { value: 'calm_condor' } })
    fireEvent.change(screen.getByLabelText('Period'), { target: { value: 'since2023' } })
    fireEvent.change(screen.getByLabelText('Option prices'), { target: { value: 'standard' } })
    fireEvent.click(screen.getByLabelText(/Trade every day/))
    fireEvent.click(screen.getByRole('button', { name: /Run the replay/ }))
    await waitFor(() =>
      expect(api.runLab).toHaveBeenCalledWith({
        algo_id: 'calm_condor',
        model: 'standard',
        gated: false,
        start: '2023-01-01',
      })
    )
  })

  it('shows the result with the edge before costs, the yearly table and the curve', async () => {
    api.runLab.mockResolvedValue(RESULT)
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Run the replay/ }))
    expect(await screen.findByText('Edge before costs')).toBeTruthy()
    expect(screen.getByText('0.54')).toBeTruthy()
    expect(screen.getByText('Costs it can bear')).toBeTruthy()
    expect(screen.getByRole('img', { name: /Running result per lot from 2023-01-03/ })).toBeTruthy()
    expect(screen.getByRole('cell', { name: '2024' })).toBeTruthy()
    expect(screen.getByText(/Zen does not trade a volatile market: 103 days/)).toBeTruthy()
  })

  it('always puts the caveats beside the numbers', async () => {
    api.runLab.mockResolvedValue(RESULT)
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Run the replay/ }))
    expect(await screen.findByText(/not real fills/)).toBeTruthy()
    expect(screen.getByText('Read this beside the numbers')).toBeTruthy()
  })

  it('says so when the algo placed no trades', async () => {
    api.runLab.mockResolvedValue({
      ...RESULT,
      metrics: { ...metrics, trades: 0 },
      yearly: [],
      curve: [],
    })
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Run the replay/ }))
    expect(await screen.findByText(/placed no trades/)).toBeTruthy()
  })

  it("shows the server's sentence when the replay fails, and nothing technical", async () => {
    api.runLab.mockRejectedValue(
      new Error(
        'Could not download market history. Check your internet connection and try again in a minute.'
      )
    )
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Run the replay/ }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/internet connection/)
    expect(alert.textContent).not.toMatch(/status code|Error:|undefined/i)
  })

  it('tells the trader the first run can take a while, and disables the button meanwhile', async () => {
    let finish: (v: LabResult) => void = () => {}
    api.runLab.mockReturnValue(
      new Promise<LabResult>((resolve) => {
        finish = resolve
      })
    )
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Run the replay/ }))
    expect(await screen.findByText(/first run downloads market history/)).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: /Run the replay/ }) as HTMLButtonElement).disabled
    ).toBe(true)
    finish(RESULT)
    expect(await screen.findByText('Edge before costs')).toBeTruthy()
  })

  it('never uses the word armed anywhere a trader reads', async () => {
    api.runLab.mockResolvedValue(RESULT)
    const { container } = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Run the replay/ }))
    await screen.findByText('Edge before costs')
    expect(container.textContent?.toLowerCase()).not.toMatch(/\barm(ed|ing)?\b/)
  })
})
