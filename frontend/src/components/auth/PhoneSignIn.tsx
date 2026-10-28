import { Loader2, Smartphone } from 'lucide-react'
import { useState } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export interface PhoneSignInResult {
  status: string
  username?: string
  broker?: string
  redirect?: string
}

interface Props {
  onResult: (result: PhoneSignInResult) => void
  onBack: () => void
}

async function csrfToken(): Promise<string> {
  const response = await fetch('/auth/csrf-token', { credentials: 'include' })
  if (!response.ok) throw new Error('csrf')
  return (await response.json()).csrf_token
}

async function post(path: string, body: unknown) {
  const token = await csrfToken()
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
    body: JSON.stringify(body),
  })
  return { ok: response.ok, data: await response.json().catch(() => ({})) }
}

export function PhoneSignIn({ onResult, onBack }: Props) {
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const request = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { ok, data } = await post('/auth/phone/request', { phone })
      if (!ok) setError(data.message || 'The code could not be requested. Please try again.')
      else {
        setSent(true)
        setNote(data.message)
      }
    } catch {
      setError('Could not reach the server. Please refresh the page and try again.')
    } finally {
      setBusy(false)
    }
  }

  const verify = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { ok, data } = await post('/auth/phone/verify', { phone, code })
      if (!ok || data.status === 'error') {
        setError(data.message || 'That code did not work. Ask for a new one.')
        setCode('')
      } else onResult(data)
    } catch {
      setError('Could not reach the server. Please refresh the page and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={sent ? verify : request} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="phone">Mobile number</Label>
        <Input
          id="phone"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="98765 43210"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          disabled={busy || sent}
          required
        />
      </div>

      {sent && (
        <div className="space-y-2">
          <Label htmlFor="phone_code">Code from the text message</Label>
          <Input
            id="phone_code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="123456"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            disabled={busy}
            autoFocus
            required
            className="font-mono text-center text-lg tracking-widest"
          />
          {note && <p className="text-sm text-muted-foreground">{note}</p>}
        </div>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" className="w-full" disabled={busy || (sent && code.length !== 6)}>
        {busy ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <Smartphone className="mr-2 h-4 w-4" />
        )}
        {sent ? 'Sign in' : 'Send code'}
      </Button>

      {sent && (
        <Button
          type="button"
          variant="ghost"
          className="w-full"
          onClick={() => {
            setSent(false)
            setCode('')
            setNote(null)
          }}
        >
          Use a different number or ask again
        </Button>
      )}
      <Button type="button" variant="link" className="w-full" onClick={onBack}>
        Sign in with a password instead
      </Button>
    </form>
  )
}
