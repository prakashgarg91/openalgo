import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { algoQueryKeys, closePick, fetchPicks, type TrackedPick } from '@/api/algos'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { showToast } from '@/utils/toast'

const rupees = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '-'
  const whole = Math.round(value)
  return `${whole < 0 ? '-' : ''}Rs ${Math.abs(whole).toLocaleString('en-IN')}`
}

const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? '-' : `${Math.round(value * 100)}%`

function errorText(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || fallback
}

function openedText(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

const legsText = (pick: TrackedPick) =>
  pick.legs.map((leg) => `${leg.kind} ${leg.strike} ${leg.side} x${leg.qty}`).join(', ')

function ResultCell({ pick }: { pick: TrackedPick }) {
  if (pick.status === 'open') {
    if (pick.unrealized === null || pick.unrealized === undefined) {
      return <span className="text-muted-foreground">no price</span>
    }
    return (
      <span className={pick.unrealized >= 0 ? 'text-green-600' : 'text-red-500'}>
        now {rupees(pick.unrealized)}
      </span>
    )
  }
  if (pick.pnl === null || pick.pnl === undefined) {
    return <span className="text-muted-foreground">-</span>
  }
  return (
    <span className={pick.pnl >= 0 ? 'text-green-600' : 'text-red-500'}>{rupees(pick.pnl)}</span>
  )
}

function PickRow({
  pick,
  busy,
  onClose,
}: {
  pick: TrackedPick
  busy: boolean
  onClose: (id: string, pnl?: number) => void
}) {
  const [typed, setTyped] = useState('')
  const typedValid = typed.trim() !== '' && Number.isFinite(Number(typed))

  return (
    <tr className="border-b align-top">
      <td className="py-2 pr-3">
        <div className="font-medium">{pick.name}</div>
        <div className="max-w-[260px] text-xs text-muted-foreground">{legsText(pick)}</div>
      </td>
      <td className="whitespace-nowrap pr-3">{openedText(pick.opened)}</td>
      <td className="whitespace-nowrap pr-3">{pick.expiry}</td>
      <td className="pr-3 font-mono">{pick.fit.toFixed(0)}</td>
      <td className="whitespace-nowrap pr-3">{rupees(pick.capital_required)}</td>
      <td className="whitespace-nowrap pr-3 font-mono">
        <ResultCell pick={pick} />
      </td>
      <td className="pr-3">
        <Badge variant="outline">{pick.status}</Badge>
      </td>
      <td>
        {pick.status === 'open' ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" disabled={busy} onClick={() => onClose(pick.id)}>
              Close at live price
            </Button>
            <input
              type="number"
              aria-label={`Your result for ${pick.name} in rupees`}
              className="h-8 w-28 rounded-md border bg-background px-2 text-sm"
              value={typed}
              disabled={busy}
              onChange={(event) => setTyped(event.target.value)}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={busy || !typedValid}
              onClick={() => {
                if (typedValid) onClose(pick.id, Number(typed))
              }}
            >
              Close at my result
            </Button>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">Closed</span>
        )}
      </td>
    </tr>
  )
}

export function PicksPanel() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: algoQueryKeys.picks(),
    queryFn: fetchPicks,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  })
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({})

  async function close(id: string, pnl?: number) {
    const confirmed = window.confirm(
      'Close this tracked pick now? The result is recorded and cannot be changed.'
    )
    if (!confirmed) return
    setBusyIds((old) => ({ ...old, [id]: true }))
    try {
      await closePick(id, pnl)
      showToast.success('Pick closed.', 'system')
      await queryClient.invalidateQueries({ queryKey: algoQueryKeys.picks() })
    } catch (error) {
      showToast.error(errorText(error, 'Could not close this pick.'), 'system')
    } finally {
      setBusyIds((old) => ({ ...old, [id]: false }))
    }
  }

  const picks = data?.picks ?? []
  const summary = data?.summary

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1.5">
            <CardTitle className="text-base">My tracked picks</CardTitle>
            <CardDescription>
              Strategies you picked from the Strategy picker, followed with live prices. Nothing
              here places an order. After about 20 closed picks it shows whether the fit score meant
              anything.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isError ? (
          <p role="alert" className="text-sm text-red-500">
            Your tracked picks could not be loaded. Check that you are signed in to Upstox.
          </p>
        ) : isLoading || !data || !summary ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Following your tracked picks.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge variant="outline">Open {summary.open}</Badge>
              <Badge variant="outline">Closed {summary.closed}</Badge>
              <Badge variant="outline">Win rate {percent(summary.win_rate)}</Badge>
              <Badge variant="outline">Average {rupees(summary.average_pnl)}</Badge>
              <Badge variant="outline">Worst {rupees(summary.worst)}</Badge>
              <Badge variant="outline">Best {rupees(summary.best)}</Badge>
              <Badge variant="outline">Total {rupees(summary.total)}</Badge>
              <Badge variant="outline">
                Correlation{' '}
                {summary.correlation === null || summary.correlation === undefined
                  ? '-'
                  : summary.correlation.toFixed(2)}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">{summary.verdict}</p>

            {picks.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No tracked picks yet. Open the Strategy picker and press Track on a strategy to
                follow it with live prices.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-muted-foreground">
                    <tr>
                      <th className="py-1 pr-3 font-normal">Strategy</th>
                      <th className="pr-3 font-normal">Opened</th>
                      <th className="pr-3 font-normal">Expiry</th>
                      <th className="pr-3 font-normal">Fit</th>
                      <th className="pr-3 font-normal">Capital needed</th>
                      <th className="pr-3 font-normal">Result</th>
                      <th className="pr-3 font-normal">Status</th>
                      <th className="font-normal">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {picks.map((pick) => (
                      <PickRow
                        key={pick.id}
                        pick={pick}
                        busy={Boolean(busyIds[pick.id])}
                        onClose={close}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
