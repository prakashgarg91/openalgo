import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Compass, Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { type ChooserCell, fetchBuilderJob, fetchChooserToday, rebuildChooser } from '@/api/algos'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { showToast } from '@/utils/toast'

const money = (v: number) => `Rs ${Math.round(v).toLocaleString('en-IN')}`

function cellText(c: ChooserCell) {
  return c.trades ? `${c.trades} trades, ${money(c.total)}` : 'no trades'
}

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'Something went wrong. Please try again.'
}

/** Which algo suits today's market, decided from past evidence, with every refusal explained. */
export function ChooserPanel() {
  const queryClient = useQueryClient()
  const today = useQuery({
    queryKey: ['algos', 'chooser'],
    queryFn: fetchChooserToday,
    staleTime: 60_000,
    retry: false,
  })
  const [jobId, setJobId] = useState<string | null>(null)
  const job = useQuery({
    queryKey: ['algos', 'chooser-job', jobId],
    queryFn: async () => {
      const state = await fetchBuilderJob(jobId as string)
      if (state.state === 'done') {
        await queryClient.invalidateQueries({ queryKey: ['algos', 'chooser'] })
      }
      return state
    },
    enabled: jobId !== null,
    refetchInterval: (q) => (q.state.data?.state === 'running' ? 2000 : false),
  })

  const rebuild = async () => {
    try {
      setJobId(await rebuildChooser())
    } catch (e) {
      showToast.error(errorText(e), 'system')
    }
  }
  const building = job.data?.state === 'running'
  const data = today.data

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Compass className="h-4 w-4" aria-hidden="true" />
              Which algo suits today?
            </CardTitle>
            <CardDescription>
              Decided from how each algo did on this kind of day in the past, after costs. It must
              have made money in the older years and again in the newer years.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={rebuild} disabled={building}>
            {building ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Refresh the evidence
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {today.isLoading && <p className="text-sm text-muted-foreground">Reading the market...</p>}
        {today.isError && <p className="text-sm text-destructive">{errorText(today.error)}</p>}
        {job.data?.state === 'failed' && (
          <p className="text-sm text-destructive">{job.data.message}</p>
        )}
        {data && (
          <>
            <p
              className={cn(
                'rounded-md border p-3 text-sm font-medium',
                data.decision.pick ? 'border-emerald-500/40' : 'border-muted-foreground/30'
              )}
            >
              {data.decision.headline}
            </p>
            {data.decision.candidates.length > 0 && (
              <ul className="space-y-2 text-sm">
                {data.decision.candidates.map((row) => (
                  <li key={row.algo_id} className="rounded-md border p-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{row.name}</span>
                      <span
                        className={cn(
                          'text-xs',
                          row.eligible ? 'text-emerald-600' : 'text-muted-foreground'
                        )}
                      >
                        {row.eligible ? 'Qualifies' : 'Does not qualify'}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Older years: {cellText(row.evidence)}. Newer years: {cellText(row.check)}.
                    </p>
                    {row.reasons.map((r) => (
                      <p key={r} className="text-xs">
                        Because it {r}.
                      </p>
                    ))}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted-foreground">
              {data.table
                ? `Evidence from ${data.table.first} to ${data.table.last}, split at ${data.table.split}; built ${data.table.built_at ?? 'earlier'}. Modelled option prices, not real fills.`
                : 'No evidence has been built yet. Press "Refresh the evidence" (about 10 seconds).'}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
