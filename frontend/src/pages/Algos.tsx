import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, FlaskConical, Loader2, RefreshCw, Trash2, Zap } from 'lucide-react'
import { useState } from 'react'
import {
  type AlgoItem,
  algoQueryKeys,
  checkAlgoNow,
  type Deployment,
  deployAlgo,
  fetchCatalogue,
  fetchCoverage,
  fetchRegime,
  type Plan,
  previewAlgo,
  type Regime,
  type RegimeLabel,
  removeAlgo,
  setAlgoActive,
  setAlgoLive,
} from '@/api/algos'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { showToast } from '@/utils/toast'

const REGIME_COPY: Record<RegimeLabel, string> = {
  calm: 'Calm',
  trending: 'Trending',
  volatile: 'Volatile',
  event: 'Event day',
}

const REGIME_TONE: Record<RegimeLabel, string> = {
  calm: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  trending: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  volatile: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  event: 'bg-red-500/15 text-red-700 dark:text-red-400',
}

const inr = (value: number | null | undefined) =>
  value == null ? '-' : `Rs ${Math.round(value).toLocaleString('en-IN')}`

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

function RegimeBanner() {
  const regime = useQuery({
    queryKey: algoQueryKeys.regime(),
    queryFn: fetchRegime,
    staleTime: 60_000,
    refetchInterval: 120_000,
  })
  const coverage = useQuery({ queryKey: algoQueryKeys.coverage(), queryFn: fetchCoverage })
  const data: Regime | undefined = regime.data

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Market right now</CardTitle>
          <CardDescription>
            Each algo reads this before it trades, and stands aside when it does not suit it.
          </CardDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => regime.refetch()}
          disabled={regime.isFetching}
        >
          <RefreshCw className={cn('h-4 w-4', regime.isFetching && 'animate-spin')} />
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {regime.isLoading && <p className="text-sm text-muted-foreground">Reading the market...</p>}
        {regime.isError && <p className="text-sm text-destructive">{errorText(regime.error)}</p>}
        {data && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={cn('border-transparent', REGIME_TONE[data.label])}>
                {REGIME_COPY[data.label]}
              </Badge>
              <Badge variant="outline" className="capitalize">
                {data.bias} lean
              </Badge>
              <Badge variant="outline">
                {Math.round(data.confidence * 100)}% of market data available
              </Badge>
            </div>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {data.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </>
        )}
        {coverage.data && (
          <div className="grid gap-2 border-t pt-3 text-sm sm:grid-cols-4">
            {(Object.keys(REGIME_COPY) as RegimeLabel[]).map((label) => (
              <div key={label}>
                <div className="font-medium">{REGIME_COPY[label]}</div>
                <div className="text-muted-foreground">
                  {coverage.data.regimes[label].length
                    ? coverage.data.regimes[label].join(', ').replaceAll('_', ' ')
                    : 'Stands aside'}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function PlanPreview({ plan }: { plan: Plan }) {
  return (
    <div
      className={cn(
        'rounded-md border p-3 text-sm',
        plan.action === 'trade' ? 'border-emerald-500/40' : 'border-amber-500/40'
      )}
    >
      <div className="font-medium">
        {plan.action === 'trade' ? 'Would trade today' : 'Would stand aside today'}
      </div>
      <p className="text-muted-foreground">{plan.reason}</p>
      {plan.action === 'trade' && (
        <p className="mt-1">
          {plan.lots} lot{plan.lots === 1 ? '' : 's'}, worst case {inr(plan.max_loss_inr)}
        </p>
      )}
    </div>
  )
}

function AddAlgo({ algo }: { algo: AlgoItem }) {
  const queryClient = useQueryClient()
  const [capital, setCapital] = useState('500000')
  const [plan, setPlan] = useState<Plan | null>(null)
  const amount = Number(capital)

  const preview = useMutation({
    mutationFn: () => previewAlgo(algo.id, amount),
    onSuccess: (result) => setPlan(result.plan),
    onError: (error) => showToast.error(errorText(error)),
  })
  const add = useMutation({
    mutationFn: () => deployAlgo(algo.id, amount),
    onSuccess: () => {
      showToast.success(`${algo.name} added in Sandbox mode. Turn it on to start.`)
      queryClient.invalidateQueries({ queryKey: algoQueryKeys.catalogue() })
    },
    onError: (error) => showToast.error(errorText(error)),
  })

  return (
    <div className="space-y-3">
      <div className="max-w-xs space-y-1">
        <Label htmlFor={`capital-${algo.id}`}>Capital for this algo (Rs)</Label>
        <Input
          id={`capital-${algo.id}`}
          inputMode="numeric"
          value={capital}
          onChange={(event) => {
            setCapital(event.target.value)
            setPlan(null)
          }}
        />
      </div>
      {plan && <PlanPreview plan={plan} />}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => preview.mutate()}
          disabled={!Number.isFinite(amount) || preview.isPending}
        >
          {preview.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          See what it would do today
        </Button>
        <Button onClick={() => add.mutate()} disabled={!Number.isFinite(amount) || add.isPending}>
          {add.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Add in Sandbox mode
        </Button>
      </div>
    </div>
  )
}

function DeployedAlgo({ algo, deployment }: { algo: AlgoItem; deployment: Deployment }) {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: algoQueryKeys.catalogue() })
  const [confirming, setConfirming] = useState(false)
  const [typed, setTyped] = useState('')
  const live = deployment.mode === 'live'
  const gate = deployment.live_gate
  const ceiling = deployment.max_loss_ceiling_inr

  const toggle = useMutation({
    mutationFn: (active: boolean) => setAlgoActive(deployment.id, active),
    onSuccess: refresh,
    onError: (error) => showToast.error(errorText(error)),
  })
  const check = useMutation({
    mutationFn: () => checkAlgoNow(deployment.id),
    onSuccess: (result) => {
      showToast.info(result.reason)
      refresh()
    },
    onError: (error) => showToast.error(errorText(error)),
  })
  const mode = useMutation({
    mutationFn: (enabled: boolean) =>
      setAlgoLive(deployment.id, enabled, enabled ? Number(typed) : undefined),
    onSuccess: () => {
      setConfirming(false)
      setTyped('')
      refresh()
    },
    onError: (error) => showToast.error(errorText(error)),
  })
  const remove = useMutation({
    mutationFn: () => removeAlgo(deployment.id),
    onSuccess: refresh,
    onError: (error) => showToast.error(errorText(error)),
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Switch
            id={`active-${deployment.id}`}
            checked={deployment.active}
            onCheckedChange={(value) => toggle.mutate(value)}
            disabled={toggle.isPending}
          />
          <Label htmlFor={`active-${deployment.id}`}>
            {deployment.active ? 'Active' : 'Stopped'}
          </Label>
        </div>
        <Badge variant={live ? 'destructive' : 'secondary'}>{live ? 'Live' : 'Sandbox'}</Badge>
        {deployment.position_open && <Badge variant="outline">Position open</Badge>}
        <span className="text-sm text-muted-foreground">
          Capital {inr(deployment.capital)}, worst case {inr(ceiling)}
        </span>
      </div>

      <p className="text-sm text-muted-foreground">
        Checks the market at {algo.entry_time} on every trading day.
      </p>

      {algo.overnight ? (
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          This algo holds overnight and exits at 09:45 the next morning. Log in to your broker
          before then each day, or the exit cannot be sent.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          This algo trades within the day and closes its position before the market ends.
        </p>
      )}

      <div className="rounded-md border p-3 text-sm">
        <div className="font-medium">Sandbox record</div>
        <p className="text-muted-foreground">
          {gate.record.runs} trade{gate.record.runs === 1 ? '' : 's'}, {gate.record.wins} won, net{' '}
          {inr(gate.record.net_pnl)}
        </p>
        {!gate.allowed && !live && <p className="mt-1 text-muted-foreground">{gate.reason}</p>}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => check.mutate()}
          disabled={!deployment.active || check.isPending}
        >
          {check.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Check the market now
        </Button>
        {live ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => mode.mutate(false)}
            disabled={mode.isPending || deployment.position_open}
          >
            <FlaskConical className="h-4 w-4" />
            Back to Sandbox
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfirming(true)}
            disabled={!gate.allowed || deployment.position_open}
          >
            <Zap className="h-4 w-4" />
            Go Live
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => remove.mutate()}
          disabled={remove.isPending || deployment.position_open}
        >
          <Trash2 className="h-4 w-4" />
          Remove
        </Button>
      </div>

      {confirming && !live && (
        <div className="space-y-2 rounded-md border border-destructive/40 p-3">
          <p className="text-sm">
            Live orders use real money. The most this algo can lose is {inr(ceiling)}. Type that
            number to confirm.
          </p>
          <div className="flex flex-wrap gap-2">
            <Input
              className="max-w-xs"
              inputMode="numeric"
              placeholder={ceiling == null ? '' : String(Math.round(ceiling))}
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              aria-label="Worst-case loss in rupees"
            />
            <Button
              variant="destructive"
              onClick={() => mode.mutate(true)}
              disabled={mode.isPending || typed === ''}
            >
              Go Live
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div>
        <div className="mb-1 text-sm font-medium">Recent decisions</div>
        {deployment.recent_decisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing yet. The first check runs at {algo.entry_time} on the next trading day.
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {deployment.recent_decisions.map((decision) => (
              <li key={decision.id} className="flex gap-2">
                <span className="w-36 shrink-0 text-muted-foreground">
                  {new Date(`${decision.decided_at}Z`).toLocaleString('en-IN', {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  })}
                </span>
                <span>
                  <span className="font-medium capitalize">
                    {decision.action === 'skip' ? 'Stood aside' : decision.action}
                  </span>
                  : {decision.reason}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

export default function Algos() {
  const catalogue = useQuery({ queryKey: algoQueryKeys.catalogue(), queryFn: fetchCatalogue })

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-6">
      <div>
        <h1 className="text-2xl font-semibold">Algos</h1>
        <p className="text-sm text-muted-foreground">
          Pick an algo, set the capital it may use, and turn it on. Every algo starts in Sandbox
          mode and has to prove itself there before it can go Live.
        </p>
      </div>

      <RegimeBanner />

      {catalogue.isLoading && <p className="text-sm text-muted-foreground">Loading algos...</p>}
      {catalogue.isError && (
        <p className="text-sm text-destructive">{errorText(catalogue.error)}</p>
      )}

      {catalogue.data?.map((algo) => (
        <Card key={algo.id}>
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>{algo.name}</CardTitle>
              <Badge variant="outline" className="capitalize">
                {algo.risk} risk
              </Badge>
              {algo.status === 'experimental' && <Badge variant="destructive">Experimental</Badge>}
              <Badge variant="outline">
                Trades on: {algo.allowed_regimes.map((label) => REGIME_COPY[label]).join(', ')}
              </Badge>
            </div>
            <CardDescription>{algo.summary}</CardDescription>
            {algo.evidence && (
              <p
                className={cn(
                  'text-sm',
                  algo.status === 'experimental' ? 'text-destructive' : 'text-muted-foreground'
                )}
              >
                {algo.evidence}
              </p>
            )}
          </CardHeader>
          <CardContent>
            {algo.deployment ? (
              <DeployedAlgo algo={algo} deployment={algo.deployment} />
            ) : (
              <AddAlgo algo={algo} />
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
