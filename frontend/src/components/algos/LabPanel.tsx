import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, FlaskConical, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { type AlgoItem, type LabMetrics, type LabModel, type LabResult, runLab } from '@/api/algos'
import { EquityCurve } from '@/components/algos/EquityCurve'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

const PERIODS = [
  { value: 'all', label: 'All available history' },
  { value: 'since2023', label: 'Since January 2023' },
  { value: 'last3y', label: 'Last 3 years' },
  { value: 'last1y', label: 'Last 12 months' },
] as const

type Period = (typeof PERIODS)[number]['value']

function periodStart(period: Period, now = new Date()): string | undefined {
  if (period === 'all') return undefined
  if (period === 'since2023') return '2023-01-01'
  const d = new Date(now)
  d.setFullYear(d.getFullYear() - (period === 'last3y' ? 3 : 1))
  return d.toISOString().slice(0, 10)
}

const inr = (v: number) => `Rs ${Math.round(v).toLocaleString('en-IN')}`

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string
  hint?: string
  tone?: 'good' | 'bad'
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={cn(
          'text-lg font-semibold',
          tone === 'good' && 'text-emerald-600 dark:text-emerald-400',
          tone === 'bad' && 'text-red-600 dark:text-red-400'
        )}
      >
        {value}
      </div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </div>
  )
}

function AccountBlock({ account }: { account: NonNullable<LabResult['account']> }) {
  if (account.lots < 1 || account.final_equity == null) {
    return (
      <div className="rounded-md border border-amber-500/50 p-3 text-sm">{account.message}</div>
    )
  }
  const up = (account.return_pct ?? 0) >= 0
  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="font-medium">
        On your account: Rs {Math.round(account.capital ?? 0).toLocaleString('en-IN')}, at most Rs{' '}
        {Math.round(account.max_daily_loss ?? 0).toLocaleString('en-IN')} lost in a day
      </div>
      <p className="text-sm text-muted-foreground">
        It would have traded {account.lots} lot{account.lots === 1 ? '' : 's'} at a time, risking at
        most {inr(account.worst_case_per_trade ?? 0)} per trade.
      </p>
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <Stat
          label="Ended with"
          value={inr(account.final_equity)}
          hint={`${up ? '+' : ''}${account.return_pct}% over ${account.days_traded} trades`}
          tone={up ? 'good' : 'bad'}
        />
        <Stat label="Worst day" value={inr(account.worst_day ?? 0)} tone="bad" />
        <Stat
          label="Deepest fall"
          value={inr(account.max_drawdown ?? 0)}
          hint={`${account.max_drawdown_pct}% from the peak`}
          tone="bad"
        />
        <Stat
          label="Daily limit"
          value={account.within_daily_cap ? 'Never passed' : 'Passed'}
          hint={
            account.within_daily_cap
              ? 'no day lost more than your limit'
              : `${account.cap_breaches?.length ?? 0} day(s) lost more`
          }
          tone={account.within_daily_cap ? 'good' : 'bad'}
        />
      </div>
      {account.ruined && (
        <p className="text-sm font-medium text-destructive">
          The account would have been wiped out along the way.
        </p>
      )}
      {account.curve && <EquityCurve curve={account.curve} />}
    </div>
  )
}

function Results({ result }: { result: LabResult }) {
  const m: LabMetrics = result.metrics
  const winning = m.total > 0
  return (
    <div className="space-y-4" aria-live="polite">
      <div className="text-sm text-muted-foreground">
        {result.algo_name}, {result.start} to {result.end}, {result.model.label}
        {result.gated ? '' : ', trading every day'}
      </div>
      {m.trades === 0 ? (
        <p className="text-sm">This algo placed no trades in this period.</p>
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <Stat label="Trades" value={String(m.trades)} />
            <Stat label="Won" value={`${m.win_rate}%`} />
            <Stat
              label="Average per trade"
              value={inr(m.avg)}
              hint="per lot, after costs"
              tone={m.avg >= 0 ? 'good' : 'bad'}
            />
            <Stat
              label="Profit factor"
              value={m.profit_factor == null ? 'n/a' : m.profit_factor.toFixed(2)}
              hint="above 1 means it made money"
              tone={winning ? 'good' : 'bad'}
            />
            <Stat
              label="Deepest loss run"
              value={inr(m.max_drawdown)}
              hint="peak to trough, per lot"
              tone="bad"
            />
            {m.avg_gross != null && (
              <Stat label="Edge before costs" value={inr(m.avg_gross)} hint="average, per lot" />
            )}
            {m.avg_cost != null && (
              <Stat label="Costs" value={inr(m.avg_cost)} hint="average, per lot" />
            )}
            {m.break_even_cost != null && (
              <Stat
                label="Costs it can bear"
                value={inr(m.break_even_cost)}
                hint="above this it loses money"
              />
            )}
          </div>

          {result.account && <AccountBlock account={result.account} />}

          <EquityCurve curve={result.curve} />

          {result.yearly.length > 0 && (
            <table className="w-full max-w-md text-sm">
              <caption className="mb-1 text-left font-medium">By year, per lot</caption>
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th scope="col" className="py-1 font-normal">
                    Year
                  </th>
                  <th scope="col" className="py-1 font-normal">
                    Trades
                  </th>
                  <th scope="col" className="py-1 text-right font-normal">
                    Result
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.yearly.map((y) => (
                  <tr key={y.year}>
                    <td className="py-0.5">{y.year}</td>
                    <td className="py-0.5">{y.trades}</td>
                    <td
                      className={cn(
                        'py-0.5 text-right',
                        y.total >= 0
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-red-600 dark:text-red-400'
                      )}
                    >
                      {inr(y.total)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {result.skipped.length > 0 && (
        <div className="text-sm">
          <div className="font-medium">Days it stood aside</div>
          <ul className="list-disc pl-5 text-muted-foreground">
            {result.skipped.slice(0, 5).map((s) => (
              <li key={s.reason}>
                {s.reason}: {s.days} day{s.days === 1 ? '' : 's'}
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.notes.map((n) => (
        <p key={n} className="text-sm text-muted-foreground">
          {n}
        </p>
      ))}

      <div className="rounded-md border border-amber-500/50 p-3 text-sm">
        <div className="mb-1 flex items-center gap-2 font-medium">
          <AlertTriangle className="h-4 w-4" />
          Read this beside the numbers
        </div>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          {result.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export function LabPanel({ algos }: { algos: AlgoItem[] }) {
  const [algoId, setAlgoId] = useState(algos[0]?.id ?? 'zen')
  const [model, setModel] = useState<LabModel>('conservative')
  const [period, setPeriod] = useState<Period>('all')
  const [everyDay, setEveryDay] = useState(false)
  const [capital, setCapital] = useState('100000')
  const [dailyLoss, setDailyLoss] = useState('20000')
  const [useAccount, setUseAccount] = useState(true)

  const run = useMutation({
    mutationFn: () =>
      runLab({
        algo_id: algoId,
        model,
        gated: !everyDay,
        start: periodStart(period),
        account: useAccount
          ? { capital: Number(capital), max_daily_loss: Number(dailyLoss) }
          : undefined,
      }),
  })

  const selectClass = 'h-9 rounded-md border border-input bg-background px-2 text-sm'

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <FlaskConical className="h-5 w-5" />
          <CardTitle>Lab</CardTitle>
        </div>
        <CardDescription>
          Replay an algo over real market history, with no broker needed. Nothing is traded or
          saved. Use it to understand an algo, not to prove it makes money.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1">
            <Label htmlFor="lab-algo">Algo</Label>
            <select
              id="lab-algo"
              className={selectClass}
              value={algoId}
              onChange={(e) => setAlgoId(e.target.value)}
            >
              {algos.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="lab-period">Period</Label>
            <select
              id="lab-period"
              className={selectClass}
              value={period}
              onChange={(e) => setPeriod(e.target.value as Period)}
            >
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="lab-model">Option prices</Label>
            <select
              id="lab-model"
              className={selectClass}
              value={model}
              onChange={(e) => setModel(e.target.value as LabModel)}
            >
              <option value="conservative">Cautious (recommended)</option>
              <option value="standard">Simple (flatters option sellers)</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={everyDay}
              onChange={(e) => setEveryDay(e.target.checked)}
            />
            Trade every day, ignoring the market check
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useAccount}
              onChange={(e) => setUseAccount(e.target.checked)}
            />
            Test on my account
          </label>
          {useAccount && (
            <>
              <div className="space-y-1">
                <Label htmlFor="lab-capital">Capital (Rs)</Label>
                <Input
                  id="lab-capital"
                  inputMode="numeric"
                  className="w-32"
                  value={capital}
                  onChange={(e) => setCapital(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="lab-daily-loss">Most to lose in a day (Rs)</Label>
                <Input
                  id="lab-daily-loss"
                  inputMode="numeric"
                  className="w-32"
                  value={dailyLoss}
                  onChange={(e) => setDailyLoss(e.target.value)}
                />
              </div>
            </>
          )}
          <Button onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Run the replay
          </Button>
        </div>

        {run.isPending && (
          <p className="text-sm text-muted-foreground" aria-live="polite">
            Replaying. The first run downloads market history and can take up to a minute.
          </p>
        )}
        {run.isError && (
          <p className="text-sm text-destructive" role="alert">
            {run.error instanceof Error
              ? run.error.message
              : 'The replay could not run. Try again.'}
          </p>
        )}
        {run.data && <Results result={run.data} />}
      </CardContent>
    </Card>
  )
}
