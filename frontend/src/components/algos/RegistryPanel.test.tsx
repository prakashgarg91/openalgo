import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RegistryView } from '@/api/algos'
import { RegistryPanel } from './RegistryPanel'

const api = vi.hoisted(() => ({
  fetchRegistry: vi.fn(),
  registerIdea: vi.fn(),
  fetchForwardTests: vi.fn(),
}))

vi.mock('@/api/algos', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/algos')>()),
  ...api,
}))

const view = (over: Partial<RegistryView> = {}): RegistryView => ({
  trial_count: 319,
  pass_bar: 0.025 / 319,
  next_free_month: '2027-01',
  months_used: { '2026-11': 'C1 month-end ETF window' },
  fields: { name: 'a short name', kill_rule: 'the loss at which it stops for good' },
  registrations: [],
  ...over,
})

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RegistryPanel />
    </QueryClientProvider>
  )
}

describe('RegistryPanel', () => {
  beforeEach(() => {
    api.fetchRegistry.mockReset()
    api.registerIdea.mockReset()
    api.fetchForwardTests.mockReset()
    api.fetchForwardTests.mockResolvedValue([])
  })

  it('shows the count, the bar to clear and the next free month in plain words', async () => {
    api.fetchRegistry.mockResolvedValue(view())
    mount()
    expect(await screen.findByText('319')).toBeInTheDocument()
    expect(screen.getByText('2027-01')).toBeInTheDocument()
    expect(screen.getByText(/Ideas and settings tried so far/)).toBeInTheDocument()
    expect(screen.queryByText(/paper|arm/i)).toBeNull()
  })

  it('lists a registered idea and flags one changed after it was frozen', async () => {
    api.fetchRegistry.mockResolvedValue(
      view({
        registrations: [
          {
            id: 'a-1',
            name: 'Vol scaled equity gold',
            created_at: '2027-01-04T10:00:00',
            slot: '2027-01',
            trial_numbers: [320, 320],
            pass_bar: 0.025 / 320,
            status: 'registered',
            intact: false,
          },
        ],
      })
    )
    mount()
    expect(await screen.findByText('Vol scaled equity gold')).toBeInTheDocument()
    expect(screen.getByText('changed after it was frozen')).toBeInTheDocument()
  })

  it('sends the written idea with gates and one-value settings, and shows a refusal as words', async () => {
    api.fetchRegistry.mockResolvedValue(view())
    api.registerIdea.mockRejectedValue({
      response: { data: { message: "This month's one new idea is already used by C1." } },
    })
    mount()
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'My idea' } })
    fireEvent.change(screen.getByLabelText(/Gates it must pass/), {
      target: { value: 'Positive net\n\nBeats the hold' },
    })
    fireEvent.change(screen.getByLabelText(/Settings, one value each/), {
      target: { value: 'wing = 100\nlabel = calm' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Freeze and count this idea/ }))
    await waitFor(() => expect(api.registerIdea).toHaveBeenCalled())
    expect(api.registerIdea.mock.calls[0][0]).toMatchObject({
      name: 'My idea',
      gates: ['Positive net', 'Beats the hold'],
      params: { wing: 100, label: 'calm' },
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('already used by C1')
  })

  it('lists the forward tests with their state and says nothing is a result until one has ended', async () => {
    api.fetchRegistry.mockResolvedValue(view())
    api.fetchForwardTests.mockResolvedValue([
      {
        name: 'Weekly call spread, 100 points wide (S3n)',
        state: 'running',
        verdict: null,
        completed: 3,
        trades_to_go: 23,
        net: 1200,
      },
    ])
    mount()
    expect(await screen.findByText(/Weekly call spread, 100 points wide/)).toBeInTheDocument()
    expect(screen.getByText('23')).toBeInTheDocument()
    expect(screen.getByText(/until a test has ended/)).toBeInTheDocument()
  })
})
