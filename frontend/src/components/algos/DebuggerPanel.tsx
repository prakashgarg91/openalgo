import { useMutation, useQuery } from '@tanstack/react-query'
import { Bug, CheckCircle2, CircleSlash, Info, Loader2 } from 'lucide-react'
import { useState } from 'react'
import {
  type AlgoItem,
  type DebugResult,
  type DebugStep,
  debugDay,
  fetchExplanations,
} from '@/api/algos'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

const ICON = { pass: CheckCircle2, stop: CircleSlash, info: Info } as const
const TONE = {
  pass: 'text-emerald-600',
  stop: 'text-destructive',
  info: 'text-muted-foreground',
} as const
const WORD = { pass: 'Passed', stop: 'Stopped here', info: 'For information' } as const

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'Something went wrong. Please try again.'
}

export function Steps({ steps }: { steps: DebugStep[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((step, i) => {
        const Icon = ICON[step.status]
        return (
          <li key={`${i}-${step.title}`} className="flex gap-2 text-sm">
            <Icon aria-hidden="true" className={cn('mt-0.5 h-4 w-4 shrink-0', TONE[step.status])} />
            <div>
              <span className="font-medium">{step.title}</span>
              <span className="sr-only"> ({WORD[step.status]})</span>
              <p className="text-muted-foreground">{step.detail}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export function ExplainRecent({ deploymentId }: { deploymentId: number }) {
  const [open, setOpen] = useState(false)
  const items = useQuery({
    queryKey: ['algos', 'explain', deploymentId],
    queryFn: () => fetchExplanations(deploymentId),
    enabled: open,
  })
  return (
    <details className="mt-3 border-t pt-3 text-sm" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer font-medium">Why did it do that?</summary>
      <div className="mt-2 space-y-3">
        {items.isLoading && <p className="text-muted-foreground">Loading...</p>}
        {items.data?.length === 0 && (
          <p className="text-muted-foreground">No decisions yet. It has not run a daily check.</p>
        )}
        {items.data?.map((item) => (
          <div key={`${item.decided_at}-${item.verdict}`} className="rounded-md border p-2">
            <p className="font-medium">{item.verdict}</p>
            <p className="mb-1 text-xs text-muted-foreground">{item.decided_at}</p>
            <Steps steps={item.steps} />
          </div>
        ))}
      </div>
    </details>
  )
}

/** Pick an algo and a past day; see, step by step, what it saw and why it traded or sat out. */
export function DebuggerPanel({ algos }: { algos: AlgoItem[] }) {
  const choices = algos.filter((a) => a.id !== 'smart_pick')
  const [algoId, setAlgoId] = useState(choices[0]?.id ?? 'zen')
  const [date, setDate] = useState('')
  const run = useMutation<DebugResult>({ mutationFn: () => debugDay(algoId, date) })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Bug className="h-4 w-4" aria-hidden="true" />
          Why did it do that?
        </CardTitle>
        <CardDescription>
          Choose an algo and a past trading day. You get what the market looked like, what kind of
          day it was, which rule let the algo trade or stopped it, and what the model says happened.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="debug_algo">Algo</Label>
            <select
              id="debug_algo"
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={algoId}
              onChange={(e) => setAlgoId(e.target.value)}
            >
              {choices.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="debug_date">Day</Label>
            <Input
              id="debug_date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-44"
            />
          </div>
          <Button onClick={() => run.mutate()} disabled={!date || run.isPending}>
            {run.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Explain that day
          </Button>
        </div>
        {run.isError && <p className="text-sm text-destructive">{errorText(run.error)}</p>}
        {run.data && (
          <div className="space-y-3">
            <p className="font-medium">{run.data.verdict}</p>
            <Steps steps={run.data.steps} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
