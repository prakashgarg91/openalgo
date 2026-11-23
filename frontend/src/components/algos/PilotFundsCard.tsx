import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { algoQueryKeys } from '@/api/algos'
import { webClient } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

// Same client and credentials handling as fetchPicker in api/algos.ts: base
// `/algos/api`, session cookie via webClient, which also copies the server's
// own `message` onto the error for us.
const BASE = '/algos/api'

export interface PilotFunds {
  sold_symbol: string
  long_symbol: string
  quantity: number
  spot: number
  margin_total: number
  premium: number
  margin_excl_premium: number
  buffer: number
  needed: number
  available_cash: number
  short_by: number
  enough: boolean
  expiry: string
  as_of: string
}

export async function fetchPilotFunds(): Promise<PilotFunds> {
  const response = await webClient.get<{ data: PilotFunds }>(`${BASE}/pilot-funds`)
  return response.data.data
}

function rupees(value: number): string {
  return `Rs ${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'Could not check funds right now. Sign in to Upstox and try again.'
}

function localTime(asOf: string): string | null {
  const time = new Date(asOf)
  return Number.isNaN(time.getTime())
    ? null
    : time.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}

/** What one lot of today's pilot spread costs, next to the cash that is there. */
export function PilotFundsCard() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: [...algoQueryKeys.all, 'pilot-funds'],
    queryFn: fetchPilotFunds,
    staleTime: 300_000,
    retry: false,
    refetchOnWindowFocus: false,
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Funds for the pilot</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Checking with Upstox...
          </p>
        </CardContent>
      </Card>
    )
  }

  if (isError || !data) {
    return (
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Funds for the pilot</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-destructive">{errorText(error)}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            Check again
          </Button>
        </CardContent>
      </Card>
    )
  }

  const rows: { label: string; value: string; strong?: boolean }[] = [
    { label: 'Margin the broker asks', value: rupees(data.margin_excl_premium) },
    { label: 'Bought call premium', value: rupees(data.premium) },
    { label: 'Safety buffer', value: rupees(data.buffer) },
    { label: 'Total needed', value: rupees(data.needed), strong: true },
    { label: 'Cash in your Upstox account', value: rupees(data.available_cash) },
  ]
  const checkedAt = localTime(data.as_of)

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-base">Funds for the pilot</CardTitle>
        <CardDescription>
          One lot of today's 200-wide call spread: sell {data.sold_symbol}, buy {data.long_symbol}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="space-y-1.5 text-sm">
          {rows.map((row) => (
            <div key={row.label} className="flex items-baseline justify-between gap-4">
              <dt className={row.strong ? 'font-semibold' : 'text-muted-foreground'}>
                {row.label}
              </dt>
              <dd className={cn('font-mono', row.strong && 'font-semibold')}>{row.value}</dd>
            </div>
          ))}
        </dl>
        <p
          className={cn('text-sm font-medium', data.enough ? 'text-emerald-600' : 'text-amber-600')}
        >
          {data.enough
            ? 'You have enough for one lot.'
            : `Short by ${rupees(data.short_by)}. Add this before the pilot.`}
        </p>
        <div className="flex items-center justify-between gap-3 border-t pt-3">
          {checkedAt && <p className="text-xs text-muted-foreground">Checked at {checkedAt}</p>}
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            Check again
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
