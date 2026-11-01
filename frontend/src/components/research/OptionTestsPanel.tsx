import type { CostData, MomentumData, SpreadData, StructuresData } from '@/api/research'
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
  cost,
  structures,
}: {
  spread?: SpreadData
  momentum?: MomentumData
  cost?: CostData
  structures?: StructuresData
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
      {cost ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Does a realistic cost model change it? Only for one rule, and only thinly
            </CardTitle>
            <CardDescription>
              The same trades, with each trade's cost recomputed: Rs 20 an order, the current
              securities tax (0.10 percent, 0.15 percent from April 2026), GST, stamp duty, the lot
              size by date and 0.15 points of slippage a fill. That is about Rs{' '}
              {cost.rows[0]?.cost_per_trade_realistic} a trade, against about Rs{' '}
              {cost.rows[0]?.cost_per_trade_conservative} in the earlier model. The slippage figure
              is an assumption until the bid and ask snapshots measure it.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Side rule</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead className="text-right">Before costs</TableHead>
                  <TableHead className="text-right">Earlier cost model</TableHead>
                  <TableHead className="text-right">Realistic costs</TableHead>
                  <TableHead className="text-right">At twice the costs</TableHead>
                  <TableHead className="text-right">Worst drawdown</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cost.rows
                  .flatMap((r) => [
                    {
                      key: `${r.rule}-sel`,
                      rule: r.rule,
                      period: 'First two thirds',
                      pre: r.sel_pre_cost,
                      cons: r.sel_conservative,
                      real: r.sel_realistic,
                      real2: r.sel_realistic_2x,
                      dd: r.sel_drawdown,
                    },
                    {
                      key: `${r.rule}-held`,
                      rule: r.rule,
                      period: 'Last third',
                      pre: r.held_pre_cost,
                      cons: r.held_conservative,
                      real: r.held_realistic,
                      real2: r.held_realistic_2x,
                      dd: r.held_drawdown,
                    },
                  ])
                  .map((x) => (
                    <TableRow key={x.key}>
                      <TableCell className="font-medium">{x.rule}</TableCell>
                      <TableCell className="text-muted-foreground">{x.period}</TableCell>
                      <TableCell className={cn('text-right tabular-nums', tone(x.pre))}>
                        {rupees(x.pre)}
                      </TableCell>
                      <TableCell className={cn('text-right tabular-nums', tone(x.cons))}>
                        {rupees(x.cons)}
                      </TableCell>
                      <TableCell className={cn('text-right tabular-nums', tone(x.real))}>
                        {rupees(x.real)}
                      </TableCell>
                      <TableCell className={cn('text-right tabular-nums', tone(x.real2))}>
                        {rupees(x.real2)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{rupees(-x.dd)}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
            <p className="mt-3 text-sm text-muted-foreground">
              Rules A and B lose even before costs, so costs are not what sinks them. Always selling
              calls turns positive under realistic costs but goes negative again at twice those
              costs, and its drawdown is far beyond a Rs 20,000 loss limit. It is also a bet on a
              falling market. Nothing here can pass: the last third has been seen before.
            </p>
          </CardContent>
        </Card>
      ) : null}
      {structures ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Other structures: the ones that sell only calls made money, but none passed
            </CardTitle>
            <CardDescription>
              No stop and no reversal; the weekly ones are held to expiry. Results are in rupees for
              one lot under the realistic cost model. A structure passed only if it kept its
              drawdown within Rs 20,000 and cleared a statistical test in the last third. The last
              third had already been seen, so even a pass would only mean a trial on new days in
              sandbox mode.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Structure</TableHead>
                  <TableHead className="text-right">First two thirds</TableHead>
                  <TableHead className="text-right">At twice the costs</TableHead>
                  <TableHead className="text-right">Last third</TableHead>
                  <TableHead className="text-right">At twice the costs</TableHead>
                  <TableHead className="text-right">Worst drawdown</TableHead>
                  <TableHead>Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {structures.rows.map((r) => (
                  <TableRow key={r.name}>
                    <TableCell className="font-medium">{r.label}</TableCell>
                    <TableCell className={cn('text-right tabular-nums', tone(r.sel_realistic))}>
                      {rupees(r.sel_realistic)}
                    </TableCell>
                    <TableCell className={cn('text-right tabular-nums', tone(r.sel_realistic_2x))}>
                      {rupees(r.sel_realistic_2x)}
                    </TableCell>
                    <TableCell className={cn('text-right tabular-nums', tone(r.held_realistic))}>
                      {rupees(r.held_realistic)}
                    </TableCell>
                    <TableCell className={cn('text-right tabular-nums', tone(r.held_realistic_2x))}>
                      {rupees(r.held_realistic_2x)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {rupees(-r.held_drawdown)}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className="bg-muted font-normal text-muted-foreground"
                      >
                        {r.passed
                          ? 'Passed'
                          : r.candidate
                            ? r.failed.includes('drawdown')
                              ? 'Too much drawdown, not proven'
                              : 'Within the loss limit, not proven'
                            : 'Lost money, dropped'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-3 text-sm text-muted-foreground">
              Taking away the stop is what changed the picture. The weekly condors, which also sell
              puts, lost money; the call-only structures earned money under realistic costs, but the
              250-point ones drew down Rs 26,000 to Rs 27,000 on one lot, above a Rs 20,000 loss
              limit. A 100-point weekly call spread stays inside the limit and earns about Rs 35,000
              in each period, but with only about 30 weekly trades in the last third the profit is
              too uneven to prove the average day is positive. They sell upside, so a sharp rally is
              their risk. Nothing here is a result to trade on; the only clean test left is new days
              in sandbox mode.
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
