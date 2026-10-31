import type { VrpData } from '@/api/research'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const num = (v: number, d = 1) => v.toLocaleString('en-IN', { maximumFractionDigits: d })

export function PremiumPanel({ data }: { data: VrpData }) {
  const all = data.periods[2]
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          [
            'India VIX above what followed',
            `${Math.round(all.positive * 100)}%`,
            'of all days since 2008',
          ],
          ['Average premium', `${num(all.premium_pts)} pts`, 'volatility points over 5 days'],
          [
            'Worst 1 percent of days',
            num(all.worst, 0),
            `against an average of ${num(all.payoff)}`,
          ],
          [
            'Selling only when it looks rich',
            'Did not help',
            `top minus bottom group: t = ${num(data.top_minus_bottom.t, 2)}`,
          ],
        ].map(([label, value, hint]) => (
          <Card key={label}>
            <CardContent className="space-y-1 p-4">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="text-2xl font-semibold tabular-nums">{value}</p>
              <p className="text-xs text-muted-foreground">{hint}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Does India VIX pay more than the market delivers?
          </CardTitle>
          <CardDescription>
            Premium is India VIX minus the volatility the Nifty actually produced over the next five
            trading days. Payoff is what a seller of that volatility would have kept, with no cap
            and no costs, so it is a guide to the idea and not to a real spread.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Period</TableHead>
                <TableHead className="text-right">Days</TableHead>
                <TableHead className="text-right">Premium (pts)</TableHead>
                <TableHead className="text-right">Payoff</TableHead>
                <TableHead className="text-right">Strength</TableHead>
                <TableHead className="text-right">Days positive</TableHead>
                <TableHead className="text-right">Worst 1%</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.periods.map((r) => (
                <TableRow key={r.label}>
                  <TableCell className="font-medium">{r.label}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.days, 0)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.premium_pts, 2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.payoff)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.t)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Math.round(r.positive * 100)}%
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.worst, 0)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-3 text-sm text-muted-foreground">
            The premium is positive in both halves. It is paid for with tail risk: most days pay a
            little and a few days take back many times the average. With the February to April 2020
            fall left out, the later period is clearly positive; with it in, it is not separate from
            zero.
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Sell only when the premium looks fat? It did not work
          </CardTitle>
          <CardDescription>
            2017 to 2026, days sorted into five groups by the premium expected before the day, using
            a forecast that explains {Math.round(data.forecast_r2 * 100)}% of the volatility that
            followed.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Group</TableHead>
                <TableHead className="text-right">Days</TableHead>
                <TableHead className="text-right">Premium (pts)</TableHead>
                <TableHead className="text-right">Payoff</TableHead>
                <TableHead className="text-right">Strength</TableHead>
                <TableHead className="text-right">Worst 1%</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.quintiles.map((r) => (
                <TableRow key={r.group}>
                  <TableCell className="font-medium">
                    {r.group === 1
                      ? '1 (lowest expected)'
                      : r.group === 5
                        ? '5 (highest expected)'
                        : r.group}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.days, 0)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.premium_pts, 2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.payoff)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.t)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(r.worst, 0)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-3 text-sm text-muted-foreground">
            The richest-looking days did no better than the others, and they hold the biggest
            losses. A rule that sells only when the premium looks fat is not supported.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
