import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AlgosTodayCard } from './AlgosTodayCard'

const api = vi.hoisted(() => ({ fetchCatalogue: vi.fn() }))
vi.mock('@/api/algos', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/algos')>()),
  ...api,
}))

function algo(deployment: unknown) {
  return { id: 'zen', name: 'Zen', entry_time: '15:05', deployment }
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AlgosTodayCard />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('AlgosTodayCard', () => {
  it('invites the trader to pick one when nothing is set up', async () => {
    api.fetchCatalogue.mockResolvedValue([algo(null)])
    show()
    expect(await screen.findByText(/No algo is set up yet/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Pick one' }).getAttribute('href')).toBe('/algos')
  })

  it('shows state, mode and the last decision in words', async () => {
    api.fetchCatalogue.mockResolvedValue([
      algo({
        active: true,
        mode: 'sandbox',
        recent_decisions: [{ action: 'skip', reason: 'Volatile market, so it sat out.' }],
      }),
    ])
    show()
    expect(await screen.findByText('Active')).toBeTruthy()
    expect(screen.getByText('Sandbox')).toBeTruthy()
    expect(screen.getByText(/Sat out: Volatile market/)).toBeTruthy()
  })

  it('says when it will check next if it has not decided yet', async () => {
    api.fetchCatalogue.mockResolvedValue([
      algo({ active: true, mode: 'sandbox', recent_decisions: [] }),
    ])
    show()
    expect(await screen.findByText('Waits for its daily check at 15:05.')).toBeTruthy()
  })

  it('stays out of the way when the algos cannot be loaded', async () => {
    api.fetchCatalogue.mockRejectedValue(new Error('x'))
    const { container } = show()
    await new Promise((r) => setTimeout(r, 30))
    expect(container.textContent).toBe('')
  })
})
