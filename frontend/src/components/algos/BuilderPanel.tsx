import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Hammer, Loader2 } from 'lucide-react'
import { useState } from 'react'
import {
  algoQueryKeys,
  type BuilderFamily,
  type BuilderResult,
  type BuilderStats,
  deleteBuiltAlgo,
  fetchBuilderJob,
  fetchProposal,
  saveBuiltAlgo,
  startBuilderSearch,
} from '@/api/algos'
import { EquityCurve } from '@/components/algos/EquityCurve'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { showToast } from '@/utils/toast'

const FAMILIES: { id: BuilderFamily; label: string }[] = [
  { id: 'condor', label: 'Iron condor' },
  { id: 'bull_put', label: 'Bull put spread' },
  { id: 'bear_call', label: 'Bear call spread' },
]

const DAYS = [
  { id: 'calm', label: 'Calm days only', sets: [['calm']] },
  { id: 'both', label: 'Calm and trending days', sets: [['calm', 'trending']] },
  { id: 'either', label: 'Try both', sets: [['calm'], ['calm', 'trending']] },
] as const

const inr = (v: number | null | undefined) =>
  v == null ? '-' : `Rs ${Math.round(v).toLocaleString('en-IN')}`

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'Something went wrong. Please try again.'
}

function StatsRow({ label, stats, dim }: { label: string; stats?: BuilderStats; dim?: boolean }) {
  return (
    <tr className={cn('border-t', dim && 'text-muted-foreground')}>
      <th scope="row" className="py-1 pr-3 text-left font-normal">
        {label}
      </th>
      <td className="pr-3 text-right">{stats ? stats.trades : '-'}</td>
      <td className={cn('pr-3 text-right', stats && stats.total < 0 && 'text-destructive')}>
        {stats ? inr(stats.total) : '-'}
      </td>
      <td className="pr-3 text-right">{stats?.profit_factor ?? '-'}</td>
      <td className="text-right">{stats ? inr(stats.max_drawdown) : '-'}</td>
    </tr>
  )
}

export function BuilderResultView({ jobId, result }: { jobId: string; result: BuilderResult }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const winner = result.winner
  const seg = result.segments

  const save = async () => {
    setSaving(true)
    try {
      await saveBuiltAlgo(jobId, name)
      showToast.success('Saved. It is in the list above, in Sandbox mode.', 'system')
      await queryClient.invalidateQueries({ queryKey: algoQueryKeys.catalogue() })
      setName('')
    } catch (e) {
      showToast.error(errorText(e), 'system')
    } finally {
      setSaving(false)
    }
  }

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
        It tried {result.trials} configurations. {result.lost_on_test} of them lost money on the
        last period, which no choice was based on. The more that is tried, the likelier one looks
        good by luck.
      </p>

      {winner && (
        <>
          <p className="text-sm">
            Best found: <span className="font-medium">{winner.name}</span>
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th className="pr-3 font-normal">Period (per lot)</th>
                  <th className="pr-3 text-right font-normal">Trades</th>
                  <th className="pr-3 text-right font-normal">Result</th>
                  <th className="pr-3 text-right font-normal">Profit factor</th>
                  <th className="text-right font-normal">Worst drawdown</th>
                </tr>
              </thead>
              <tbody>
                <StatsRow
                  label={`Chosen on: ${seg.train[0]} to ${seg.train[1]}`}
                  stats={winner.train}
                  dim
                />
                <StatsRow
                  label={`Checked on: ${seg.validate[0]} to ${seg.validate[1]}`}
                  stats={winner.validate}
                />
                <StatsRow
                  label={`Never seen: ${seg.test[0]} to ${seg.test[1]}`}
                  stats={winner.test}
                />
                <StatsRow
                  label="Calm Condor on the never-seen period"
                  stats={result.baseline_test ?? undefined}
                  dim
                />
              </tbody>
            </table>
          </div>
          {winner.curve && <EquityCurve curve={winner.curve} />}
        </>
      )}

      {result.shortlist.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            Other finalists ({result.shortlist.length}), shown on the periods used to choose
          </summary>
          <ul className="mt-2 space-y-1">
            {result.shortlist.map((c) => (
              <li key={c.name}>
                {c.name}: chosen-on {inr(c.train.total)}, checked-on {inr(c.validate.total)}
              </li>
            ))}
          </ul>
        </details>
      )}

      {winner && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="built_name">Name</Label>
            <Input
              id="built_name"
              value={name}
              maxLength={60}
              onChange={(e) => setName(e.target.value)}
              placeholder="My bull put"
              className="w-56"
            />
          </div>
          <Button onClick={save} disabled={saving || !name.trim()}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save to my algos (Sandbox)
          </Button>
        </div>
      )}

      <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
        {result.caveats.map((c) => (
          <li key={c}>{c}</li>
        ))}
        <li>
          A saved algo is only a candidate. It has to run in Sandbox and then show real fills before
          it deserves money.
        </li>
      </ul>
    </div>
  )
}

export function BuilderPanel() {
  const [families, setFamilies] = useState<BuilderFamily[]>(['condor', 'bull_put'])
  const [days, setDays] = useState<(typeof DAYS)[number]['id']>('either')
  const [jobId, setJobId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const job = useQuery({
    queryKey: ['algos', 'builder-job', jobId],
    queryFn: () => fetchBuilderJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (q) => (q.state.data?.state === 'running' ? 2000 : false),
  })

  const toggle = (id: BuilderFamily) =>
    setFamilies((prev) => (prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]))

  const start = async () => {
    setStarting(true)
    setError(null)
    setJobId(null)
    try {
      const sets = DAYS.find((d) => d.id === days)?.sets ?? []
      setJobId(await startBuilderSearch({ families, label_sets: sets.map((s) => [...s]) }))
    } catch (e) {
      setError(errorText(e))
    } finally {
      setStarting(false)
    }
  }

  const data = job.data
  const running = starting || data?.state === 'running'
  const count = families.length * 5 * 2 * (days === 'either' ? 2 : 1)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Hammer className="h-4 w-4" aria-hidden="true" />
          <CardTitle>Build and refine your own</CardTitle>
        </div>
        <CardDescription>
          Pick the kinds of trade and the kinds of day. The search tries every combination on past
          years, chooses on the early years, checks on the middle years, and then reads the best one
          on the last years it never saw. It will tell you plainly when nothing holds up.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Trades to try</legend>
          {FAMILIES.map((f) => (
            <label key={f.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={families.includes(f.id)}
                onChange={() => toggle(f.id)}
              />
              {f.label}
            </label>
          ))}
        </fieldset>

        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Days to trade</legend>
          {DAYS.map((d) => (
            <label key={d.id} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="builder_days"
                checked={days === d.id}
                onChange={() => setDays(d.id)}
              />
              {d.label}
            </label>
          ))}
        </fieldset>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={start} disabled={running || families.length === 0}>
            {running && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {running ? 'Searching...' : 'Search'}
          </Button>
          <span className="text-sm text-muted-foreground">
            Tries {count} configurations. Takes about a minute. Costs are included.
          </span>
        </div>

        {data?.state === 'running' && data.progress.total ? (
          <progress className="h-2 w-full" value={data.progress.done} max={data.progress.total}>
            {data.progress.done} of {data.progress.total}
          </progress>
        ) : null}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {data?.state === 'failed' && <p className="text-sm text-destructive">{data.message}</p>}
        {data?.state === 'done' && jobId && (
          <BuilderResultView jobId={jobId} result={data.result} />
        )}
      </CardContent>
    </Card>
  )
}

/** Shown on a card for an algo the trader built: re-check it against newer data, or delete it. */
export function BuiltAlgoTools({ customId, deployed }: { customId: number; deployed: boolean }) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const job = useQuery({
    queryKey: ['algos', 'builder-review', jobId],
    queryFn: () => fetchBuilderJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (q) => (q.state.data?.state === 'running' ? 2000 : false),
  })

  const recheck = async () => {
    setError(null)
    setJobId(null)
    try {
      setJobId(
        await startBuilderSearch({
          families: ['condor', 'bull_put', 'bear_call'],
          label_sets: [['calm'], ['calm', 'trending']],
          custom_id: customId,
        })
      )
    } catch (e) {
      setError(errorText(e))
    }
  }

  const remove = async () => {
    try {
      await deleteBuiltAlgo(customId)
      await queryClient.invalidateQueries({ queryKey: algoQueryKeys.catalogue() })
    } catch (e) {
      showToast.error(errorText(e), 'system')
    }
  }

  const data = job.data
  const waiting = useQuery({
    queryKey: ['algos', 'proposal', customId],
    queryFn: () => fetchProposal(customId),
    staleTime: 60_000,
  })
  return (
    <div className="mt-3 space-y-2 border-t pt-3 text-sm">
      {waiting.data?.proposal && (
        <p className="rounded-md border border-amber-500/40 p-2">
          The weekly check on {waiting.data.checked_on} found a setup that looks better:{' '}
          <span className="font-medium">{waiting.data.proposal.name}</span>.{' '}
          {waiting.data.proposal.why} Nothing was changed. To use it, build it above and save it as
          a new algo.
        </p>
      )}
      {waiting.data && !waiting.data.proposal && (
        <p className="text-muted-foreground">
          Weekly check on {waiting.data.checked_on}: no change recommended.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={recheck} disabled={data?.state === 'running'}>
          Check for a better version
        </Button>
        <Button variant="outline" size="sm" onClick={remove} disabled={deployed}>
          Delete
        </Button>
        {deployed && (
          <span className="self-center text-muted-foreground">
            Remove it from your deployed algos first.
          </span>
        )}
      </div>
      {error && <p className="text-destructive">{error}</p>}
      {data?.state === 'running' && (
        <p className="text-muted-foreground">Searching on newer data...</p>
      )}
      {data?.state === 'failed' && <p className="text-destructive">{data.message}</p>}
      {data?.state === 'done' && (
        <p>
          {data.result.proposal ? (
            <>
              A different setup looks better:{' '}
              <span className="font-medium">{data.result.proposal.name}</span>.{' '}
              {data.result.proposal.why} Nothing was changed. If you want it, build it above and
              save it as a new algo.
            </>
          ) : (
            <>No change recommended. {data.result.verdict.headline}</>
          )}
        </p>
      )}
    </div>
  )
}
