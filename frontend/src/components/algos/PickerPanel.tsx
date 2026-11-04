import { useQuery } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { algoQueryKeys, fetchPicker, type PickerRow } from '@/api/algos'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const rupees = (value: number | null | undefined) =>
  value === null || value === undefined ? '-' : `Rs ${Math.round(value).toLocaleString('en-IN')}`

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'The picker could not be loaded. Check that you are signed in to Upstox.'
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
      <td className="py-2 text-right font-mono">{rupees(row.costs?.total)}</td>
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
            <th className="py-2 text-right">Costs, in and out</th>
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
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: algoQueryKeys.picker(),
    queryFn: () => fetchPicker(true),
    refetchInterval: 120_000,
    retry: false,
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Pricing every structure from the live chain.
        This takes up to half a minute.
      </div>
    )
  }
  if (isError || !data) {
    return <p className="text-sm text-red-500">{errorText(error)}</p>
  }
  const h = data.header
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div>
              <CardTitle>Strategy picker</CardTitle>
              <CardDescription>
                Every structure priced live: what it can earn and lose, the capital it needs, and
                how well today suits it. You choose. Nothing here places an order.
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={`mr-1 h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} /> Refresh
            </Button>
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
          <p className="text-xs text-muted-foreground">
            Earn and loss figures are for one lot held to expiry. Capital needed is the broker's
            margin ({h.margins_from_broker ?? 0} structures) or the premium paid. Costs are the
            charges plus the gap between buy and sell prices for getting in and out once.
          </p>
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
          <CardDescription>Highest fit first. Fit is not a forecast of profit.</CardDescription>
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
