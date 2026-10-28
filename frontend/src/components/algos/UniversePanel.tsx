import { useQuery } from '@tanstack/react-query'
import { Globe2, Loader2 } from 'lucide-react'
import { useState } from 'react'
import {
  fetchBuilderJob,
  startUniverseSearch,
  type UniverseResult,
  type UniverseStats,
} from '@/api/algos'
import { EquityCurve } from '@/components/algos/EquityCurve'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

const inr = (v: number) => `Rs ${Math.round(v).toLocaleString('en-IN')}`

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'Something went wrong. Please try again.'
}

function Row({ label, s, dim }: { label: string; s: UniverseStats; dim?: boolean }) {
  return (
    <tr className={cn('border-t', dim && 'text-muted-foreground')}>
      <th scope="row" className="py-1 pr-3 text-left font-normal">
        {label}
      </th>
      <td className="pr-3 text-right">{s.cagr.toFixed(1)}% a year</td>
      <td className="pr-3 text-right">{inr(s.max_drawdown)}</td>
      <td className="text-right">{inr(s.worst_day)}</td>
    </tr>
  )
}

export function UniverseResultView({ result }: { result: UniverseResult }) {
  const seg = result.segments
  const w = result.winner
  const acct = result.account
  return (
    <div className="space-y-4">
      <p
        className={cn(
          'rounded-md border p-3 text-sm',
          result.verdict.edge_shown ? 'border-emerald-500/40' : 'border-destructive/40'
        )}
      >
        <span className="font-medium">{result.verdict.headline}</span>
        {result.verdict.reasons.map((r) => (
          <span key={r} className="block text-muted-foreground">
            {r}
          </span>
        ))}
      </p>
      <p className="text-sm text-muted-foreground">
        It tried {result.trials} rules on {result.data_from} to {result.data_to}.{' '}
        {result.lost_to_cash_on_test} of them earned less than cash on the last period, which no
        choice was based on.
      </p>
      <p className="text-sm">
        Best found: <span className="font-medium">{w.name}</span>
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="pr-3 font-normal">Period</th>
              <th className="pr-3 text-right font-normal">Return</th>
              <th className="pr-3 text-right font-normal">Deepest fall</th>
              <th className="text-right font-normal">Worst day</th>
            </tr>
          </thead>
          <tbody>
            <Row label={`Chosen on: ${seg.train[0]} to ${seg.train[1]}`} s={w.stats.train} dim />
            <Row
              label={`Checked on: ${seg.validate[0]} to ${seg.validate[1]}`}
              s={w.stats.validate}
            />
            <Row label={`Never seen: ${seg.test[0]} to ${seg.test[1]}`} s={w.stats.test} />
            <Row
              label="Buy and hold the Nifty ETF, never seen"
              s={result.baselines.buy_and_hold.test}
              dim
            />
            <Row label="Leave it in cash (6%), never seen" s={result.baselines.cash.test} dim />
          </tbody>
        </table>
      </div>
      {acct.final_equity != null && (
        <div className="space-y-2 rounded-md border p-3 text-sm">
          <div className="font-medium">
            Your account on the never-seen period: {inr(acct.capital ?? 0)}, at most{' '}
            {inr(acct.max_daily_loss ?? 0)} lost in a day
          </div>
          <p>
            It would have ended with <b>{inr(acct.final_equity)}</b> ({acct.return_pct}%). Worst day{' '}
            {inr(acct.worst_day ?? 0)}, deepest fall {inr(acct.max_drawdown ?? 0)}.{' '}
            {acct.within_daily_cap
              ? 'No day passed your daily limit.'
              : 'Some days passed your daily limit.'}
          </p>
          {acct.curve && <EquityCurve curve={acct.curve} />}
        </div>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">
          All {result.rules.length} rules on the never-seen period (for reading, not for choosing)
        </summary>
        <ul className="mt-2 space-y-1">
          {result.rules.map((r) => (
            <li key={r.name} className="flex flex-wrap gap-x-3">
              <span className="font-mono text-xs">{r.name}</span>
              <span
                className={cn(
                  r.test_excess_over_cash >= 0 ? 'text-emerald-600' : 'text-destructive'
                )}
              >
                {r.test_cagr.toFixed(1)}% a year ({r.test_excess_over_cash >= 0 ? '+' : ''}
                {inr(r.test_excess_over_cash)} vs cash)
              </span>
            </li>
          ))}
        </ul>
      </details>
      <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
        {result.caveats.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
    </div>
  )
}

export function UniversePanel() {
  const [capital, setCapital] = useState('100000')
  const [dailyLoss, setDailyLoss] = useState('20000')
  const [jobId, setJobId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const job = useQuery({
    queryKey: ['algos', 'universe-job', jobId],
    queryFn: () => fetchBuilderJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (q) => (q.state.data?.state === 'running' ? 2000 : false),
  })

  const start = async () => {
    setStarting(true)
    setError(null)
    setJobId(null)
    try {
      setJobId(
        await startUniverseSearch({ capital: Number(capital), max_daily_loss: Number(dailyLoss) })
      )
    } catch (e) {
      setError(errorText(e))
    } finally {
      setStarting(false)
    }
  }

  const data = job.data
  const running = starting || data?.state === 'running'
  const result =
    data?.state === 'done' && (data.result as unknown as UniverseResult).kind === 'universe'
      ? (data.result as unknown as UniverseResult)
      : null

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Globe2 className="h-4 w-4" aria-hidden="true" />
          <CardTitle>Search every kind of algo</CardTitle>
        </div>
        <CardDescription>
          Not only option spreads: trend following, rotating between the Nifty ETF and gold, buying
          dips, calendar rules. It judges them against leaving the money in cash and against simply
          buying and holding, on years it was not chosen on. Needs an internet connection (about 20
          seconds).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="uni-capital">Capital (Rs)</Label>
            <Input
              id="uni-capital"
              inputMode="numeric"
              className="w-32"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="uni-loss">Most to lose in a day (Rs)</Label>
            <Input
              id="uni-loss"
              inputMode="numeric"
              className="w-32"
              value={dailyLoss}
              onChange={(e) => setDailyLoss(e.target.value)}
            />
          </div>
          <Button onClick={start} disabled={running}>
            {running && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {running ? 'Searching...' : 'Search everything'}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {data?.state === 'failed' && <p className="text-sm text-destructive">{data.message}</p>}
        {result && <UniverseResultView result={result} />}
      </CardContent>
    </Card>
  )
}
