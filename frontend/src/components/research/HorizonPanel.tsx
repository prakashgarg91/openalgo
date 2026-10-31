import type { HorizonData } from '@/api/research'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const pct = (v: number) => `${(v * 100).toFixed(1)}%`

export function HorizonPanel({ data }: { data: HorizonData }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Looking a week and a month ahead</CardTitle>
            <CardDescription>
              {data.pairs_tried} links tried between markets (1, 5, 20 and 60 day moves) and what
              the Nifty does over the next 5 and 20 days. {data.selected} stood out in 2008 to 2017
              and {data.verified} held in 2017 to 2026; about {pct(data.chance_mean)} would by luck.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Outcome</TableHead>
                  <TableHead className="text-right">Found</TableHead>
                  <TableHead className="text-right">Held up</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.outcomes.map((o) => (
                  <TableRow key={o.outcome}>
                    <TableCell className="font-medium">{o.label}</TableCell>
                    <TableCell className="text-right tabular-nums">{o.selected}</TableCell>
                    <TableCell className="text-right tabular-nums">{o.verified}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-3 text-sm text-muted-foreground">
              Direction over a week or a month: nothing held up. Volatility: almost everything that
              was found held up, because volatility is predictable.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Do more markets help the forecast?</CardTitle>
            <CardDescription>
              Share of each outcome explained on 2017 to 2026 data the model never saw. The simple
              baseline is India VIX, the Nifty's own 20-day volatility and its 20-day return.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Outcome</TableHead>
                  <TableHead className="text-right">Baseline</TableHead>
                  <TableHead className="text-right">All markets</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.joint_model.map((m) => (
                  <TableRow key={m.label}>
                    <TableCell className="font-medium">{m.label}</TableCell>
                    <TableCell className="text-right tabular-nums">{pct(m.r2_baseline)}</TableCell>
                    <TableCell className="text-right tabular-nums">{pct(m.r2_full)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-3 text-sm text-muted-foreground">
              Adding every market makes the forecast worse, not better. Three numbers already carry
              what can be known about volatility.
            </p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Strongest links that held up</CardTitle>
          <CardDescription>
            Effect is the change in log volatility for one standard deviation of the input. A
            negative sign on a market's recent move means volatility is higher after it fell.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Input</TableHead>
                <TableHead>Affects</TableHead>
                <TableHead className="text-right">Effect</TableHead>
                <TableHead className="text-right">Strength</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.top_links.map((l) => (
                <TableRow key={`${l.input}-${l.outcome}`}>
                  <TableCell className="font-medium">{l.input}</TableCell>
                  <TableCell>{l.outcome}</TableCell>
                  <TableCell className="text-right tabular-nums">{l.beta_ver.toFixed(3)}</TableCell>
                  <TableCell className="text-right tabular-nums">{l.t_ver.toFixed(1)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
