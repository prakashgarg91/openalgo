import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PhoneSignIn } from './PhoneSignIn'

const fetchMock = vi.fn()

function reply(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) })
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation((url: string) => {
    if (url === '/auth/csrf-token') return reply({ csrf_token: 't' })
    if (url === '/auth/phone/request')
      return reply({ status: 'success', message: 'A code is on its way.' })
    return reply({ status: 'success', broker: 'upstox' })
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

describe('PhoneSignIn', () => {
  it('asks for the number, then the code, then signs in', async () => {
    const onResult = vi.fn()
    render(<PhoneSignIn onResult={onResult} onBack={() => {}} />)
    fireEvent.change(screen.getByLabelText('Mobile number'), { target: { value: '98765 43210' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send code' }))
    const code = await screen.findByLabelText('Code from the text message')
    expect(screen.getByText('A code is on its way.')).toBeTruthy()
    fireEvent.change(code, { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() =>
      expect(onResult).toHaveBeenCalledWith({ status: 'success', broker: 'upstox' })
    )
    const verify = fetchMock.mock.calls.find((c) => c[0] === '/auth/phone/verify')
    expect(JSON.parse(verify?.[1].body)).toEqual({ phone: '98765 43210', code: '123456' })
  })

  it('shows the server message in plain words when the code is refused', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === '/auth/csrf-token') return reply({ csrf_token: 't' })
      if (url === '/auth/phone/request') return reply({ status: 'success', message: 'Sent.' })
      return reply(
        { status: 'error', message: 'That code is wrong or has expired. Ask for a new one.' },
        false
      )
    })
    const onResult = vi.fn()
    render(<PhoneSignIn onResult={onResult} onBack={() => {}} />)
    fireEvent.change(screen.getByLabelText('Mobile number'), { target: { value: '9876543210' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send code' }))
    fireEvent.change(await screen.findByLabelText('Code from the text message'), {
      target: { value: '000000' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText(/wrong or has expired/)).toBeTruthy()
    expect(onResult).not.toHaveBeenCalled()
  })

  it('can go back to the password form', () => {
    const onBack = vi.fn()
    render(<PhoneSignIn onResult={() => {}} onBack={onBack} />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in with a password instead' }))
    expect(onBack).toHaveBeenCalled()
  })
})
