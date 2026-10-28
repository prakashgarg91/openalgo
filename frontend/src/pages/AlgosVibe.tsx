import { useQuery } from '@tanstack/react-query'
import {
  type Bot,
  Hammer,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Sunrise,
  TrendingUp,
  Waves,
} from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router'
import {
  type AlgoItem,
  algoQueryKeys,
  fetchCatalogue,
  fetchReadiness,
  fetchRegime,
  type RegimeLabel,
} from '@/api/algos'
import { BuilderPanel, BuiltAlgoTools } from '@/components/algos/BuilderPanel'
import { LabPanel } from '@/components/algos/LabPanel'
import { ReadinessPanel, StartHere } from '@/components/algos/ReadinessPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { AddAlgo, DeployedAlgo, errorText, REGIME_COPY, REGIME_TONE } from './AlgosClassic'

const MOOD: Record<RegimeLabel, { icon: typeof Waves; line: string }> = {
  calm: { icon: Waves, line: 'Quiet markets. Good for algos that collect small premiums.' },
  trending: { icon: TrendingUp, line: 'The market is leaning one way. Some algos follow it.' },
  volatile: { icon: Sparkles, line: 'Wild swings. Most algos sit this one out.' },
  event: { icon: Sparkles, line: 'Big-news day. Most algos sit this one out.' },
}

const ALGO_ICON: Record<string, typeof Bot> = {
  zen: Sparkles,
  mirror_zen: Moon,
  morning_gap: Sunrise,
  calm_condor: ShieldCheck,
}

const TAGLINE: Record<string, string> = {
  zen: 'Sells a cushion of risk on the side the market favours, and holds it overnight.',
  mirror_zen: "Zen's opposite twin: bets the market will not follow through.",
  morning_gap: 'Fades a big opening gap and closes the same day.',
  calm_condor: 'Earns if the market stays in a range. Calm days only.',
}

function MoodStrip() {
  const regime = useQuery({
    queryKey: algoQueryKeys.regime(),
    queryFn: fetchRegime,
    staleTime: 60_000,
    refetchInterval: 120_000,
  })
  const readiness = useQuery({
    queryKey: algoQueryKeys.readiness(),
    queryFn: fetchReadiness,
    staleTime: 30_000,
  })
  const data = regime.data
  const todo = readiness.data?.steps.filter((s) => s.state === 'todo').length ?? 0

  let body: ReactNode
  if (regime.isLoading) body = <Skeleton className="h-10 w-full" />
  else if (regime.isError)
    body = <p className="text-sm text-destructive">{errorText(regime.error)}</p>
  else if (data && !data.reliable)
    body = (
      <output className="block text-sm">
        <span className="font-medium">Cannot read the market yet.</span>{' '}
        <span className="text-muted-foreground">
          Only {Math.round(data.confidence * 100)}% of the data is in, so algos sit out. Check your
          broker connection, then refresh.
        </span>
      </output>
    )
  else if (data) {
    const mood = MOOD[data.label]
    const Icon = mood.icon
    body = (
      <div className="flex items-center gap-3">
        <span className={cn('rounded-full p-2', REGIME_TONE[data.label])}>
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <div className="font-semibold">
            Today: {REGIME_COPY[data.label]}
            <span className="ml-2 text-sm font-normal capitalize text-muted-foreground">
              {data.bias} lean
            </span>
          </div>
          <p className="text-sm text-muted-foreground">{mood.line}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">{body}</div>
      <div className="flex items-center gap-2">
        {readiness.data && (
          <Badge
            variant="outline"
            className={cn(todo === 0 ? 'text-emerald-600' : 'text-amber-600')}
          >
            {todo === 0 ? 'Ready for Live' : `Live: ${todo} thing${todo > 1 ? 's' : ''} to do`}
          </Badge>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label="Refresh the market read"
          onClick={() => regime.refetch()}
          disabled={regime.isFetching}
        >
          <RefreshCw className={cn('h-4 w-4', regime.isFetching && 'animate-spin')} />
        </Button>
      </div>
    </div>
  )
}

function scoreChip(algo: AlgoItem): { text: string; className: string } {
  if (algo.id.startsWith('custom_'))
    return {
      text: 'Built by you',
      className: 'bg-violet-500/15 text-violet-700 dark:text-violet-400',
    }
  if (algo.status === 'experimental')
    return {
      text: 'Lost money in our tests',
      className: 'bg-destructive/10 text-destructive',
    }
  return { text: 'Tested', className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400' }
}

function AlgoTile({ algo, onTry }: { algo: AlgoItem; onTry: () => void }) {
  const Icon = ALGO_ICON[algo.id] ?? Hammer
  const chip = scoreChip(algo)
  const active = algo.deployment !== null
  return (
    <Card className="flex flex-col">
      <CardHeader className="space-y-2 pb-2">
        <div className="flex items-start justify-between gap-2">
          <span className="rounded-lg bg-muted p-2">
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', chip.className)}>
            {chip.text}
          </span>
        </div>
        <CardTitle className="text-base">{algo.name}</CardTitle>
        <CardDescription>{TAGLINE[algo.id] ?? algo.summary}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto space-y-3">
        <div className="flex flex-wrap gap-1.5 text-xs">
          <Badge variant="outline" className="capitalize">
            {algo.risk} risk
          </Badge>
          <Badge variant="outline">
            Trades on {algo.allowed_regimes.map((l) => REGIME_COPY[l].toLowerCase()).join(' + ')}{' '}
            days
          </Badge>
        </div>
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">How it works and how it tested</summary>
          <p className="mt-1">{algo.summary}</p>
          {algo.evidence && <p className="mt-1">{algo.evidence}</p>}
        </details>
        <Button className="w-full" variant={active ? 'outline' : 'default'} onClick={onTry}>
          {active ? 'Open in My algos' : 'Try it in Sandbox'}
        </Button>
      </CardContent>
    </Card>
  )
}

export default function AlgosVibe() {
  const catalogue = useQuery({ queryKey: algoQueryKeys.catalogue(), queryFn: fetchCatalogue })
  const [tab, setTab] = useState('discover')
  const [adding, setAdding] = useState<AlgoItem | null>(null)
  const items = catalogue.data ?? []
  const mine = items.filter((a) => a.deployment)

  return (
    <div className="container mx-auto max-w-6xl space-y-5 px-4 py-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Algos</h1>
          <p className="text-sm text-muted-foreground">
            Pick one, give it some capital, watch it in Sandbox. Nothing risks real money until you
            say so.
          </p>
        </div>
        <Link
          to="?variant=classic"
          className="hidden text-xs text-muted-foreground underline sm:block"
        >
          Old layout
        </Link>
      </div>

      <MoodStrip />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="w-full justify-start overflow-x-auto sm:w-auto">
          <TabsTrigger value="discover">Discover</TabsTrigger>
          <TabsTrigger value="mine">
            My algos{mine.length > 0 ? ` (${mine.length})` : ''}
          </TabsTrigger>
          <TabsTrigger value="build">Build your own</TabsTrigger>
          <TabsTrigger value="lab">Test on history</TabsTrigger>
        </TabsList>

        <TabsContent value="discover" className="space-y-4 pt-3">
          {catalogue.isLoading && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-64 rounded-xl" />
              ))}
            </div>
          )}
          {catalogue.isError && (
            <p className="text-sm text-destructive">{errorText(catalogue.error)}</p>
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((algo) => (
              <AlgoTile
                key={algo.id}
                algo={algo}
                onTry={() => (algo.deployment ? setTab('mine') : setAdding(algo))}
              />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="mine" className="space-y-4 pt-3">
          {mine.length === 0 && (
            <>
              <StartHere />
              <p className="text-sm text-muted-foreground">
                Nothing here yet. Pick an algo under Discover.
              </p>
            </>
          )}
          {mine.map((algo) => (
            <Card key={algo.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{algo.name}</CardTitle>
                <CardDescription>{algo.summary}</CardDescription>
              </CardHeader>
              <CardContent>
                {algo.deployment && <DeployedAlgo algo={algo} deployment={algo.deployment} />}
                {algo.id.startsWith('custom_') && (
                  <BuiltAlgoTools customId={Number(algo.id.slice('custom_'.length))} deployed />
                )}
              </CardContent>
            </Card>
          ))}
          {items
            .filter((a) => a.id.startsWith('custom_') && !a.deployment)
            .map((algo) => (
              <Card key={algo.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{algo.name} (not added yet)</CardTitle>
                  <CardDescription>{algo.summary}</CardDescription>
                </CardHeader>
                <CardContent>
                  <AddAlgo algo={algo} />
                  <BuiltAlgoTools
                    customId={Number(algo.id.slice('custom_'.length))}
                    deployed={false}
                  />
                </CardContent>
              </Card>
            ))}
          <ReadinessPanel />
        </TabsContent>

        <TabsContent value="build" className="pt-3">
          <BuilderPanel />
        </TabsContent>

        <TabsContent value="lab" className="pt-3">
          {items.length > 0 && <LabPanel algos={items} />}
        </TabsContent>
      </Tabs>

      <Dialog open={adding !== null} onOpenChange={(open) => !open && setAdding(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{adding?.name}</DialogTitle>
            <DialogDescription>
              It starts in Sandbox and stopped. You turn it on from My algos.
            </DialogDescription>
          </DialogHeader>
          {adding && <AddAlgo algo={adding} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
