import type { MomentumData, SpreadData } from '@/api/research'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

const rupees = (v: number) => `${v < 0 ? '-' : ''}Rs ${Math.abs(v).toLocaleString('en-IN')}`
const tone = (v: number) => (v < 0 ? 'text-rose-500' : 'text-emerald-500')

export function OptionTestsPanel({
  spread,
  momentum,
}: {
  spread?: SpreadData
  momentum?: MomentumData
}) {
  return (
    <div className="space-y-4">
      {spread ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Weekly credit spread with a range gate: every cell lost money
            </CardTitle>
            <CardDescription>
              Real option prices from 108 expired weekly Nifty expiries, one lot, after costs. The
              spread is sold at the money, 400 points wide, at 10:15, with a stop and a target. The
              gate stands aside on days expected to be wide. None of {spread.cells} cells qualified
              in the first two thirds, and {spread.cells_lost_held} of {spread.cells} lost money in
              the last third, which was kept back until then.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Side rule</TableHead>
                  <TableHead>Gate</TableHead>
                  <TableHead className="text-right">First two thirds</TableHead>
                  <TableHead className="text-right">At twice the costs</TableHead>
                  <TableHead className="text-right">Last third</TableHead>
                  <TableHead className="text-right">Worst drawdown</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {spread.rows.map((r) => (
                  <TableRow key={`${r.rule}-${r.gate}`}>
                    <TableCell className="font-medium">{r.rule}</TableCell>
                    <TableCell className="text-muted-foreground">{r.gate}</TableCell>
                    <TableCell className={cn('text-right tabular-nums', tone(r.sel_net))}>
                      {rupees(r.sel_net)}
                    </TableCell>
                    <TableCell className={cn('text-right tabular-nums', tone(r.sel_net_2x))}>
                      {rupees(r.sel_net_2x)}
                    </TableCell>
                    <TableCell className={cn('text-right tabular-nums', tone(r.held_net))}>
                      {rupees(r.held_net)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {rupees(-r.held_drawdown)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-3 text-sm text-muted-foreground">
              Skipping the widest-expected days made no difference, because none of these sessions
              was in that group. The always-sell-calls control lost the least. Before costs it was
              positive; the costs, roughly Rs 270 a trade, took it back. Whether that cost model is
              too harsh has not been tested. This is one falling-market period and candle prices
              with no bid and ask.
            </p>
          </CardContent>
        </Card>
      ) : null}
      {momentum ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Does the first half-hour predict the last? Not on the Nifty
            </CardTitle>
            <CardDescription>
              {momentum.sessions.toLocaleString('en-IN')} sessions from January 2022. Published work
              on the S&P 500 finds that the first half-hour predicts the last. Slopes below are for
              the last half-hour; strength of about 2 or more counts as a link. None held in both
              halves, and the combined model explains less than guessing the average (
              {(momentum.joint_r2 * 100).toFixed(1)}%).
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Days</TableHead>
                  <TableHead>Predictor</TableHead>
                  <TableHead className="text-right">First half</TableHead>
                  <TableHead className="text-right">Second half</TableHead>
                  <TableHead>Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {momentum.pairs.map((p) => (
                  <TableRow key={`${p.condition}-${p.predictor}`}>
                    <TableCell className="font-medium">{p.condition}</TableCell>
                    <TableCell>{p.predictor}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.beta_first.toFixed(3)} ({p.t_first.toFixed(1)})
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.beta_second.toFixed(3)} ({p.t_second.toFixed(1)})
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className="bg-muted font-normal text-muted-foreground"
                      >
                        {p.verified ? 'Held up' : 'Did not hold'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-3 text-sm text-muted-foreground">
              The one link that looked real in the first half (calm days, first half-hour) reversed
              its sign in the second half, which is what noise looks like. Three of twelve tests
              reaching a strength of 2 by chance is about what to expect.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
