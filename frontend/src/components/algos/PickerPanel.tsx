import { useQuery } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { algoQueryKeys, fetchPicker, type PickerHistory, type PickerRow } from '@/api/algos'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const rupees = (value: number | null | undefined) =>
  value === null || value === undefined ? '-' : `Rs ${Math.round(value).toLocaleString('en-IN')}`

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'The picker could not be loaded. Check that you are signed in to Upstox.'
}

function PastWeeks({ history }: { history: PickerHistory | null | undefined }) {
  if (!history) return <span className="text-muted-foreground">-</span>
  if (!history.available) {
    return <span className="text-xs text-muted-foreground">{history.reason}</span>
  }
  const bucket = history.today_bucket
  return (
    <div className="space-y-0.5 text-xs">
      <div className="font-mono">
        Average {rupees(history.mean)}, won {Math.round((history.win_rate ?? 0) * 100)}%
      </div>
      <div className="font-mono text-muted-foreground">
        Worst {rupees(history.worst)}, {history.trades} weeks
      </div>
      <div className="font-mono text-muted-foreground">
        Older {rupees(history.older_mean)}, recent {rupees(history.recent_mean)}
      </div>
      {bucket?.trades ? (
        <div className="font-mono">
          With VIX like today ({bucket.bucket}): {rupees(bucket.mean)}, won{' '}
          {Math.round((bucket.win_rate ?? 0) * 100)}%, {bucket.trades} weeks
        </div>
      ) : (
        <div className="text-muted-foreground">{bucket?.note}</div>
      )}
      {history.note && <div className="text-amber-600">{history.note}</div>}
    </div>
  )
}

function Row({ row, blocked }: { row: PickerRow; blocked: boolean }) {
  const stats = row.stats
  const credit = stats?.net_credit ?? 0
  return (
    <tr className="border-b align-top">
      <td className="py-2 pr-3 font-medium">
        {row.name}
        <div className="max-w-[260px] text-xs font-normal text-muted-foreground">
          {row.evidence}
        </div>
        {blocked &&
          row.blocked_because.map((reason) => (
            <div key={reason} className="max-w-[260px] text-xs font-normal text-red-500">
              {reason}
            </div>
          ))}
      </td>
      <td className="py-2 pr-3 text-right font-mono">{blocked ? '-' : row.score?.toFixed(0)}</td>
      <td className="py-2 pr-3 text-right font-mono text-green-600">
        {stats ? (stats.max_profit === null ? 'Unlimited' : rupees(stats.max_profit)) : '-'}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-red-500">
        {stats ? (stats.unbounded_loss ? 'Unlimited' : rupees(stats.max_loss)) : '-'}
      </td>
      <td className="py-2 pr-3 text-right font-mono">
        {rupees(row.capital_required)}
        <div className="text-xs text-muted-foreground">{row.capital_source}</div>
      </td>
      <td className="py-2 pr-3 text-right font-mono">
        {stats ? `${credit >= 0 ? 'Credit' : 'Debit'} ${rupees(Math.abs(credit))}` : '-'}
      </td>
      <td className="py-2 pr-3 text-right font-mono">
        {stats?.breakevens.length ? stats.breakevens.map((b) => Math.round(b)).join(', ') : '-'}
      </td>
      <td className="py-2 pr-3 text-right font-mono">{rupees(row.costs?.total)}</td>
      <td className="min-w-[210px] py-2">
        <PastWeeks history={row.history} />
      </td>
    </tr>
  )
}

function Table({ rows, blocked }: { rows: PickerRow[]; blocked: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="py-2 pr-3">Strategy</th>
            <th className="py-2 pr-3 text-right">Fit</th>
            <th className="py-2 pr-3 text-right">Most it can earn</th>
            <th className="py-2 pr-3 text-right">Most it can lose</th>
            <th className="py-2 pr-3 text-right">Capital needed</th>
            <th className="py-2 pr-3 text-right">Entry</th>
            <th className="py-2 pr-3 text-right">Breakevens</th>
            <th className="py-2 pr-3 text-right">Costs, in and out</th>
            <th className="py-2">Past weeks of the same structure</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <Row key={row.id} row={row} blocked={blocked} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function PickerPanel() {
  const [withMargins, setWithMargins] = useState(false)
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: algoQueryKeys.picker(withMargins),
    queryFn: () => fetchPicker(withMargins),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 45_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {withMargins
          ? 'Asking the broker for margins. This can take up to 15 seconds.'
          : 'Pricing every structure from the live chain.'}
      </div>
    )
  }
  if (isError || !data) {
    return <p className="text-sm text-red-500">{errorText(error)}</p>
  }
  const h = data.header
  const gap = h.research?.expected_gap
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div>
              <CardTitle>Strategy picker</CardTitle>
              <CardDescription>
                Every structure priced live: what it can earn and lose, the capital it needs, how
                well today suits it, and how the same structure did in past weeks. You choose.
                Nothing here places an order.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              {!withMargins && (
                <Button variant="outline" size="sm" onClick={() => setWithMargins(true)}>
                  Get broker margins
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                <RefreshCw className={`mr-1 h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} /> Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">Nifty {h.spot.toLocaleString('en-IN')}</Badge>
            <Badge variant="outline">
              Expiry {h.expiry} ({h.dte} days)
            </Badge>
            <Badge variant="outline">Lot {h.lot}</Badge>
            {h.vix ? <Badge variant="outline">India VIX {h.vix.toFixed(1)}</Badge> : null}
            {h.regime ? (
              <Badge variant="outline">
                {h.regime.label}, {h.regime.bias}
              </Badge>
            ) : null}
            {h.expected_move.fifteen_minutes ? (
              <Badge variant="outline">
                Typical 15-minute move {h.expected_move.fifteen_minutes} points
              </Badge>
            ) : null}
            <Badge variant="outline">
              Your limits: capital {rupees(h.capital)}, daily loss {rupees(h.daily_cap)}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">{h.disclaimer}</p>
          {h.history_note && <p className="text-xs text-muted-foreground">{h.history_note}</p>}
          <p className="text-xs text-muted-foreground">
            Earn and loss figures are for one lot held to expiry. Capital needed is the broker's
            margin ({h.margins_from_broker ?? 0} structures; press Get broker margins) or else the
            premium paid. Costs are the charges plus the gap between buy and sell prices for getting
            in and out once.
          </p>
          {h.research && (
            <div className="rounded-md border p-2 text-xs">
              <div className="font-medium">What the research data says</div>
              {gap?.gap_pct !== null && gap?.gap_pct !== undefined ? (
                <p>
                  Overseas markets today point to a Nifty opening gap of about{' '}
                  {gap.gap_pct >= 0 ? '+' : ''}
                  {gap.gap_pct.toFixed(2)} percent (
                  {gap.links
                    .map((l) => `${l.label} ${l.move_pct >= 0 ? '+' : ''}${l.move_pct.toFixed(2)}%`)
                    .join(', ')}
                  ). A rough estimate from links that held on years the study had not seen.
                </p>
              ) : (
                <p>No overseas moves were available, so there is no gap estimate.</p>
              )}
              {Object.entries(h.research.skill).map(([key, item]) => (
                <p key={key} className={item.usable ? '' : 'text-muted-foreground'}>
                  {item.note}
                </p>
              ))}
              <p className="text-muted-foreground">
                So the picker lets direction matter only before the open. After it, direction counts
                for little, and volatility, cost and your limits do most of the work.
              </p>
            </div>
          )}
          {h.notes.map((note) => (
            <p key={note} className="text-xs text-amber-600">
              {note}
            </p>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Within your limits ({data.ranked.length})</CardTitle>
          <CardDescription>
            Highest fit first. Fit is not a forecast of profit, and past weeks are not a promise.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table rows={data.ranked} blocked={false} />
        </CardContent>
      </Card>
      {data.blocked.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Outside your limits ({data.blocked.length})</CardTitle>
            <CardDescription>
              Shown so you can see why; the reason is under each name.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table rows={data.blocked} blocked />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
