import { useQuery } from '@tanstack/react-query'
import { Info, Network } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  fetchLinkage,
  type LinkageData,
  type LinkStatus,
  type ResearchLink,
  researchQueryKeys,
} from '@/api/research'
import { ChainMap } from '@/components/research/ChainMap'
import { GROUP_COLOR, LinkageMap, statusLabel } from '@/components/research/LinkageMap'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

const TARGET_ORDER = ['gap', 'intraday', 'range', 'close_to_close']

const STATUS_TONE: Record<LinkStatus, string> = {
  verified: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  weak: 'bg-slate-500/15 text-slate-700 dark:text-slate-300',
  flipped: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  not_selected: 'bg-muted text-muted-foreground',
}

const pct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)}%`

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}

function NodeDetail({
  data,
  nodeId,
  mode,
}: {
  data: LinkageData
  nodeId: string | null
  mode: 'held' | 'all'
}) {
  const names = useMemo(() => new Map(data.nodes.map((n) => [n.id, n])), [data.nodes])
  if (!nodeId) {
    return (
      <div className="space-y-2 text-sm text-muted-foreground">
        <p>Click a dot or a circle in the middle to see its links here.</p>
        <p>
          Green lines mean the two move the same way; red lines mean they move opposite ways.
          Thicker means a stronger, more reliable link. Dashed lines did not hold up.
        </p>
      </div>
    )
  }
  const node = names.get(nodeId)
  const rows = data.links
    .filter(
      (l) =>
        (l.source === nodeId || l.target === nodeId) &&
        l.status !== 'not_selected' &&
        (mode === 'all' || l.status === 'verified')
    )
    .sort((a, b) => Math.abs(b.t_ver ?? 0) - Math.abs(a.t_ver ?? 0))
  return (
    <div className="space-y-3">
      <div>
        <p className="font-semibold">{node?.label}</p>
        {node?.note ? <p className="text-xs text-muted-foreground">{node.note}</p> : null}
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No link here held up in the later years.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((l) => {
            const other = names.get(l.source === nodeId ? l.target : l.source)
            return (
              <li
                key={`${l.source}-${l.target}`}
                className="flex items-center justify-between gap-2 text-sm"
              >
                <span>{other?.label}</span>
                <span className="flex items-center gap-2">
                  <span className="tabular-nums text-muted-foreground">
                    {l.beta_ver === null ? '-' : l.beta_ver.toFixed(2)}
                  </span>
                  <Badge variant="secondary" className={cn('font-normal', STATUS_TONE[l.status])}>
                    {statusLabel(l.status)}
                  </Badge>
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function MapTab({ data }: { data: LinkageData }) {
  const [active, setActive] = useState<Set<string>>(new Set(['gap', 'range']))
  const [mode, setMode] = useState<'held' | 'all'>('held')
  const [selected, setSelected] = useState<string | null>(null)
  const targets = data.nodes.filter((n) => n.kind === 'target')

  const toggle = (id: string) => {
    const next = new Set(active)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setActive(next.size ? next : new Set([id]))
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <CardHeader className="space-y-3 pb-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">Show links to:</span>
            {TARGET_ORDER.map((id) => {
              const t = targets.find((n) => n.id === id)
              if (!t) return null
              return (
                <Button
                  key={id}
                  size="sm"
                  variant={active.has(id) ? 'default' : 'outline'}
                  onClick={() => toggle(id)}
                >
                  {t.label}
                </Button>
              )
            })}
            <span className="mx-1 hidden h-5 w-px bg-border sm:block" />
            <Button
              size="sm"
              variant={mode === 'held' ? 'default' : 'outline'}
              onClick={() => setMode('held')}
            >
              Held up only
            </Button>
            <Button
              size="sm"
              variant={mode === 'all' ? 'default' : 'outline'}
              onClick={() => setMode('all')}
            >
              Include ones that failed
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <LinkageMap
            data={data}
            activeTargets={active}
            mode={mode}
            selected={selected}
            onSelect={setSelected}
          />
          <div className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1">
            {data.groups.map((g) => (
              <span key={g.id} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span
                  className="inline-block size-2.5 rounded-full"
                  style={{ background: GROUP_COLOR[g.id] }}
                />
                {g.label}
              </span>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card className="h-fit">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Details</CardTitle>
          <CardDescription>
            The number is the Nifty move, in percent, for a 1 percent move in the other market
            (yields: for 1 point).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <NodeDetail data={data} nodeId={selected} mode={mode} />
        </CardContent>
      </Card>
    </div>
  )
}

function LinksTab({ data }: { data: LinkageData }) {
  const [target, setTarget] = useState<string>('all')
  const [status, setStatus] = useState<'held' | 'tested' | 'everything'>('held')
  const names = useMemo(() => new Map(data.nodes.map((n) => [n.id, n])), [data.nodes])
  const groupLabel = useMemo(() => new Map(data.groups.map((g) => [g.id, g.label])), [data.groups])

  const rows = useMemo(() => {
    const keep = (l: ResearchLink) => {
      if (target !== 'all' && l.target !== target) return false
      if (status === 'held') return l.status === 'verified'
      if (status === 'tested') return l.status !== 'not_selected'
      return true
    }
    return data.links
      .filter(keep)
      .sort(
        (a, b) =>
          Math.abs(b.t_ver ?? 0) - Math.abs(a.t_ver ?? 0) || Math.abs(b.t_disc) - Math.abs(a.t_disc)
      )
  }, [data.links, target, status])

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {['all', ...TARGET_ORDER].map((id) => (
            <Button
              key={id}
              size="sm"
              variant={target === id ? 'default' : 'outline'}
              onClick={() => setTarget(id)}
            >
              {id === 'all' ? 'All outcomes' : names.get(id)?.label}
            </Button>
          ))}
          <span className="mx-1 hidden h-5 w-px bg-border sm:block" />
          {(
            [
              ['held', 'Held up'],
              ['tested', 'Found, any result'],
              ['everything', 'Everything tried'],
            ] as const
          ).map(([id, label]) => (
            <Button
              key={id}
              size="sm"
              variant={status === id ? 'default' : 'outline'}
              onClick={() => setStatus(id)}
            >
              {label}
            </Button>
          ))}
        </div>
        <CardDescription>
          {rows.length} links. Strength is how sure we can be the link is not chance (about 2 or
          more is a real link). The first period is 2008 to 2017, the second 2017 to 2026.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Market</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Affects</TableHead>
              <TableHead className="text-right">Effect, first period</TableHead>
              <TableHead className="text-right">Strength</TableHead>
              <TableHead className="text-right">Effect, second period</TableHead>
              <TableHead className="text-right">Strength</TableHead>
              <TableHead>Result</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((l) => {
              const n = names.get(l.source)
              return (
                <TableRow key={`${l.source}-${l.target}`}>
                  <TableCell className="font-medium">{n?.label}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {groupLabel.get(n?.group ?? '')}
                  </TableCell>
                  <TableCell>{names.get(l.target)?.label}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {l.beta_disc.toFixed(3)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{l.t_disc.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {l.beta_ver === null ? '-' : l.beta_ver.toFixed(3)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {l.t_ver === null ? '-' : l.t_ver.toFixed(1)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={cn('font-normal', STATUS_TONE[l.status])}>
                      {statusLabel(l.status)}
                    </Badge>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function ChainsTab({ data }: { data: LinkageData }) {
  const [selected, setSelected] = useState<string | null>(null)
  const d = data.domino
  if (!d) {
    return (
      <Alert>
        <Info className="size-4" />
        <AlertDescription>The chain results are not in this copy yet.</AlertDescription>
      </Alert>
    )
  }
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Step 1: foreign move to a sector or stock"
          value={`${d.stage1.verified} of ${d.stage1.selected}`}
          hint={`held up; ${pct(d.stage1.chance_mean)} expected by luck`}
        />
        <Stat
          label="Step 2: that gap to the Nifty after the open"
          value={`${d.stage2.verified} of ${d.stage2.selected}`}
          hint={`held up; ${pct(d.stage2.chance_mean)} expected by luck`}
        />
        <Stat
          label="Chains through both steps"
          value={String(d.chains.length)}
          hint={`really ${new Set(d.chains.map((c) => `${c.middle}|${c.end}`)).size} second steps`}
        />
        <Stat
          label="Usable as an algo input"
          value="None"
          hint="the second step is too weak and decays"
        />
      </div>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Foreign market to sector or stock to the Nifty
          </CardTitle>
          <CardDescription>
            Left to right: a foreign move, the sector or stock that opens differently because of it,
            and what the Nifty does after the open. Green means the same direction, red the
            opposite. Click any name to follow its chains.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChainMap chains={d.chains} selected={selected} onSelect={setSelected} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Step 2 on its own: every link found</CardTitle>
          <CardDescription>
            Does a sector or stock opening stronger than the Nifty predict the Nifty's day? Only the
            ones marked held up passed the later period.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sector or stock</TableHead>
                <TableHead>Affects</TableHead>
                <TableHead className="text-right">Effect, first period</TableHead>
                <TableHead className="text-right">Effect, second period</TableHead>
                <TableHead>Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...d.stage2_pairs]
                .sort(
                  (a, b) =>
                    Number(b.verified) - Number(a.verified) || Math.abs(b.t_ver) - Math.abs(a.t_ver)
                )
                .map((p) => (
                  <TableRow key={`${p.middle}-${p.end}`}>
                    <TableCell className="font-medium">{p.middle_label}</TableCell>
                    <TableCell>{p.end_label}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.beta_disc.toFixed(3)} ({p.t_disc.toFixed(1)})
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.beta_ver.toFixed(3)} ({p.t_ver.toFixed(1)})
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={cn(
                          'font-normal',
                          p.verified ? STATUS_TONE.verified : STATUS_TONE.flipped
                        )}
                      >
                        {p.verified ? 'Held up' : 'Did not hold'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
          <p className="mt-3 text-sm text-muted-foreground">
            The numbers in brackets are the strength of the link. The one link to the move after the
            open (Tata Steel) fell to a fifth of its first-period size. The measure is open to
            close, so it includes the first hour that a 10:15 entry cannot trade.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function ModelsTab({ data }: { data: LinkageData }) {
  const names = new Map(data.nodes.map((n) => [n.id, n.label]))
  const top = Math.max(...data.range_model.calibration.map((c) => c.mean_range_pct))
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">How much of each outcome can be explained</CardTitle>
          <CardDescription>
            All the markets together, fitted on 2008 to 2017 and scored once on 2017 to 2026. Higher
            is better; zero means no better than guessing the average.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Outcome</TableHead>
                <TableHead className="text-right">All markets</TableHead>
                <TableHead className="text-right">Volatility only</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.joint_model.map((m) => (
                <TableRow key={m.target}>
                  <TableCell className="font-medium">{names.get(m.target) ?? m.target}</TableCell>
                  <TableCell className="text-right tabular-nums">{pct(m.r2_full)}</TableCell>
                  <TableCell className="text-right tabular-nums">{pct(m.r2_baseline)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-3 text-sm text-muted-foreground">
            The opening gap is largely explained by what the US did overnight. The move after the
            open is not. The day's range is explained almost entirely by India VIX and the previous
            day's range.
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ranking days by expected range</CardTitle>
          <CardDescription>
            Days sorted into five groups by the range we expected before the open. The bars show the
            range that actually followed. The widest group moves {data.range_model.top_to_bottom}{' '}
            times as far as the quietest.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.range_model.calibration.map((c) => (
            <div key={c.group} className="space-y-1">
              <div className="flex justify-between text-sm">
                <span>
                  {c.group === 1
                    ? 'Quietest expected'
                    : c.group === 5
                      ? 'Widest expected'
                      : `Group ${c.group}`}
                </span>
                <span className="tabular-nums text-muted-foreground">
                  {c.mean_range_pct.toFixed(2)}% over {c.days} days
                </span>
              </div>
              <div className="h-2 rounded-full bg-muted">
                <div
                  className="h-2 rounded-full bg-primary"
                  style={{ width: `${(c.mean_range_pct / top) * 100}%` }}
                />
              </div>
            </div>
          ))}
          <p className="pt-2 text-sm text-muted-foreground">
            Adding the opening India VIX, the gap, longer averages, the US VIX or the weekday did
            not improve on India VIX and the previous range alone.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function HowToRead({ data }: { data: LinkageData }) {
  const m = data.meta
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">How to read this, and what it does not tell you</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm leading-relaxed">
        <p>
          We looked at {data.nodes.filter((n) => n.kind === 'driver').length} markets, sectors and
          stocks and four things the Nifty does. Links were searched for in {m.discovery} and then
          checked, without changes, on {m.verification}. {m.selected} links stood out in the first
          period and {m.verified} of them held in the second. Shuffling the data at random would
          make about {pct(m.chance_mean)} of them hold by luck.
        </p>
        <p>
          Only information known before the Nifty opens was used: the previous US and Europe
          sessions, Asia's last close, and yesterday's Indian close. Anything that happens after
          9:15 was left out.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>
            A strong link to the opening gap is already in the price by 10:15, so it does not tell
            an algo which side to take.
          </li>
          <li>
            Links to the move after the open looked strong in 2008 to 2017 and reversed afterwards.
            A link can stop working, so weights taken from this page must be re-checked on fresh
            data.
          </li>
          <li>
            The day's range is the usable part: India VIX and yesterday's range say how wide the day
            is likely to be, which matters for stops and strike distance.
          </li>
          <li>
            Not covered yet: news, institutional flows, GIFT Nifty, and chains of effects through
            several steps (for example crude, then the rupee, then banks, then the Nifty).
          </li>
        </ul>
        <Alert>
          <Info className="size-4" />
          <AlertDescription>
            This page is research. Nothing here places an order, and no algo uses these links yet. A
            link only becomes an input after it improves a rule written down in advance and runs in
            sandbox mode on new days.
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  )
}

export default function Research() {
  const query = useQuery({
    queryKey: researchQueryKeys.linkage(),
    queryFn: fetchLinkage,
    staleTime: 10 * 60_000,
  })

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 p-4 md:p-6">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-primary/10 p-2 text-primary">
          <Network className="size-5" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Research</h1>
          <p className="text-sm text-muted-foreground">
            Which foreign markets, sectors and stocks move with the Nifty, and whether the link
            lasted. Updated {query.data?.generated ?? '...'}.
          </p>
        </div>
      </div>

      {query.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      ) : query.isError || !query.data ? (
        <Alert>
          <Info className="size-4" />
          <AlertDescription>
            {query.error instanceof Error
              ? query.error.message
              : 'The research results could not be loaded. Try again in a moment.'}
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label="Links found, 2008 to 2017"
              value={String(query.data.meta.selected)}
              hint={`out of ${query.data.meta.pairs_tried} tried`}
            />
            <Stat
              label="Held up, 2017 to 2026"
              value={String(query.data.meta.verified)}
              hint={`${query.data.meta.flipped} reversed direction`}
            />
            <Stat
              label="Expected by luck alone"
              value={pct(query.data.meta.chance_mean)}
              hint={`vs ${pct(query.data.meta.verified / query.data.meta.selected, 0)} that held`}
            />
            <Stat
              label="US close explains the gap"
              value={pct(query.data.joint_model.find((m) => m.target === 'gap')?.r2_full ?? 0, 0)}
              hint="but not the move after the open"
            />
          </div>
          <Tabs defaultValue="map">
            <TabsList>
              <TabsTrigger value="map">Map</TabsTrigger>
              <TabsTrigger value="links">All links</TabsTrigger>
              <TabsTrigger value="chains">Chains</TabsTrigger>
              <TabsTrigger value="models">Models</TabsTrigger>
              <TabsTrigger value="read">How to read</TabsTrigger>
            </TabsList>
            <TabsContent value="map" className="mt-4">
              <MapTab data={query.data} />
            </TabsContent>
            <TabsContent value="links" className="mt-4">
              <LinksTab data={query.data} />
            </TabsContent>
            <TabsContent value="chains" className="mt-4">
              <ChainsTab data={query.data} />
            </TabsContent>
            <TabsContent value="models" className="mt-4">
              <ModelsTab data={query.data} />
            </TabsContent>
            <TabsContent value="read" className="mt-4">
              <HowToRead data={query.data} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  )
}
