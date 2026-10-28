import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventDaysPanel } from './EventDaysPanel'

const api = vi.hoisted(() => ({
  fetchEventDays: vi.fn(),
  addEventDay: vi.fn(),
  removeEventDay: vi.fn(),
}))
vi.mock('@/api/algos', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/algos')>()),
  ...api,
}))

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <EventDaysPanel />
    </QueryClientProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('EventDaysPanel', () => {
  it('lists days, adds one, and says it also covers the day before', async () => {
    api.fetchEventDays.mockResolvedValue([])
    api.addEventDay.mockResolvedValue([{ date: '2026-02-01', label: 'Union Budget' }])
    show()
    expect(await screen.findByText('No days listed.')).toBeTruthy()
    expect(screen.getByText(/trading day before it/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Day'), { target: { value: '2026-02-01' } })
    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'Union Budget' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('Union Budget')).toBeTruthy()
    expect(api.addEventDay).toHaveBeenCalledWith('2026-02-01', 'Union Budget')
  })

  it('shows the plain refusal from the server', async () => {
    api.fetchEventDays.mockResolvedValue([])
    api.addEventDay.mockRejectedValue({
      response: { data: { message: 'Pick a day from today to about a year ahead.' } },
    })
    show()
    fireEvent.change(await screen.findByLabelText('Day'), { target: { value: '2020-01-01' } })
    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText(/from today to about a year ahead/)).toBeTruthy()
  })

  it('removes a day', async () => {
    api.fetchEventDays.mockResolvedValue([{ date: '2026-02-01', label: 'Union Budget' }])
    api.removeEventDay.mockResolvedValue([])
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(api.removeEventDay).toHaveBeenCalledWith('2026-02-01'))
    expect(await screen.findByText('No days listed.')).toBeTruthy()
  })
})
