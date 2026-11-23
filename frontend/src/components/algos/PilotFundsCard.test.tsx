/**
 * What this pins.
 *
 * The card is the trader's go/no-go for the pilot day: the numbers must come
 * from /algos/api/pilot-funds over the session client, the shortage must be
 * said in rupees, and a failed check must show the server's own sentence,
 * never a status code or a machine term.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { type PilotFunds, PilotFundsCard } from './PilotFundsCard'

const web = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/api/client', () => ({ webClient: web }))

function payload(overrides: Partial<PilotFunds> = {}): PilotFunds {
  return {
    sold_symbol: 'NIFTY23NOV2625300CE',
    long_symbol: 'NIFTY23NOV2625500CE',
    quantity: 65,
    spot: 25283.0,
    margin_total: 49898.0,
    premium: 4127.0,
    margin_excl_premium: 45771.0,
    buffer: 4577.1,
    needed: 54475.1,
    available_cash: 32041.0,
    short_by: 22434.1,
    enough: false,
    expiry: '2026-11-23',
    as_of: '2026-11-23T10:20:00+05:30',
    ...overrides,
  }
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PilotFundsCard />
    </QueryClientProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('PilotFundsCard', () => {
  it('asks /algos/api/pilot-funds with the session client', async () => {
    web.get.mockResolvedValue({ data: { data: payload() } })
    show()
    await screen.findByText('Total needed')
    expect(web.get).toHaveBeenCalledWith('/algos/api/pilot-funds')
  })

  it('shows what one lot needs and the shortage in rupees', async () => {
    web.get.mockResolvedValue({ data: { data: payload() } })
    show()
    expect(await screen.findByText('Total needed')).toBeTruthy()
    expect(screen.getByText('Funds for the pilot')).toBeTruthy()
    expect(screen.getByText(/sell NIFTY23NOV2625300CE, buy NIFTY23NOV2625500CE\./)).toBeTruthy()
    expect(screen.getByText('Total needed')).toBeTruthy()
    expect(screen.getByText('Rs 54,475')).toBeTruthy()
    expect(screen.getByText(/Short by Rs 22,434\. Add this before the pilot\./)).toBeTruthy()
    expect(screen.queryByText(/You have enough/)).toBeNull()
  })

  it('says the trader has enough when cash covers the lot', async () => {
    web.get.mockResolvedValue({
      data: { data: payload({ enough: true, available_cash: 60000, short_by: 0 }) },
    })
    show()
    expect(await screen.findByText('You have enough for one lot.')).toBeTruthy()
    expect(screen.queryByText(/Short by/)).toBeNull()
  })

  it('shows the server message when the check fails', async () => {
    web.get.mockRejectedValue({
      response: {
        status: 400,
        data: { status: 'error', message: 'Sign in to Upstox first, then check again.' },
      },
    })
    show()
    expect(await screen.findByText('Sign in to Upstox first, then check again.')).toBeTruthy()
  })

  it('falls back to plain words when there is no server message', async () => {
    web.get.mockRejectedValue(new Error('Network Error'))
    show()
    expect(
      await screen.findByText('Could not check funds right now. Sign in to Upstox and try again.')
    ).toBeTruthy()
  })

  it('waits while Upstox answers', () => {
    web.get.mockReturnValue(new Promise(() => {}))
    show()
    expect(screen.getByText('Checking with Upstox...')).toBeTruthy()
  })

  it('checks again on the button, not on its own', async () => {
    web.get.mockResolvedValue({ data: { data: payload() } })
    show()
    await screen.findByText('Total needed')
    expect(web.get).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    await waitFor(() => expect(web.get).toHaveBeenCalledTimes(2))
  })
})
