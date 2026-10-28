import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { webClient } from '@/api/client'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { showToast } from '@/utils/toast'

interface PhoneState {
  enabled: boolean
  phone: string | null
}

function message(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || fallback
}

export function PhoneRegistration() {
  const queryClient = useQueryClient()
  const state = useQuery({
    queryKey: ['phone-login'],
    queryFn: async () => (await webClient.get<PhoneState>('/auth/phone/me')).data,
  })
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!state.data) return null
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['phone-login'] })

  const send = async () => {
    setBusy(true)
    setError(null)
    try {
      await webClient.post('/auth/phone/register/request', { phone })
      setSent(true)
    } catch (e) {
      setError(message(e, 'The code could not be sent. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      await webClient.post('/auth/phone/register/verify', { phone, code })
      showToast.success('Phone number saved', 'system')
      setSent(false)
      setCode('')
      setPhone('')
      await refresh()
    } catch (e) {
      setError(message(e, 'That code did not work. Ask for a new one.'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await webClient.delete('/auth/phone/me')
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Phone sign-in</CardTitle>
        <CardDescription>
          Sign in with a text message code instead of your password. Only the number saved here can
          be used.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!state.data.enabled && (
          <Alert>
            <AlertDescription>
              Phone sign-in is switched off on this server. Add an SMS provider to your .env file to
              turn it on (see docs/algos/phone-login.md).
            </AlertDescription>
          </Alert>
        )}

        {state.data.phone && (
          <div className="flex items-center justify-between text-sm">
            <span>
              Saved number: <span className="font-mono">{state.data.phone}</span>
            </span>
            <Button variant="outline" size="sm" onClick={remove} disabled={busy}>
              Remove
            </Button>
          </div>
        )}

        {state.data.enabled && (
          <div className="space-y-2">
            <Label htmlFor="register_phone">
              {state.data.phone ? 'Change your number' : 'Mobile number'}
            </Label>
            <Input
              id="register_phone"
              type="tel"
              placeholder="98765 43210"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={busy || sent}
            />
            {sent && (
              <>
                <Label htmlFor="register_code">Code from the text message</Label>
                <Input
                  id="register_code"
                  inputMode="numeric"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  disabled={busy}
                />
              </>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button
              onClick={sent ? confirm : send}
              disabled={busy || !phone || (sent && code.length !== 6)}
            >
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {sent ? 'Save number' : 'Send code'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
