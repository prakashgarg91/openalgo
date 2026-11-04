import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import {
  algoQueryKeys,
  fetchPicker,
  type PickerHistory,
  type PickerRow,
  trackPick,
} from '@/api/algos'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { showToast } from '@/utils/toast'

const rupees = (value: number | null | undefined) =>
  value === null || value === undefined ? '-' : `Rs ${Math.round(value).toLocaleString('en-IN')}`

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'The picker could not be loaded. Check that you are signed in to Upstox.'
}

function PastWeeks({ history }: { history: PickerHistory | null | undefined }) {
  if (!history) return <span className="text-muted-foreground">-</span>
  if (!history.available) {
    return <span className="text-xs text-muted-foreground">{history.reason}</span>
  }
  const bucket = history.today_bucket
  return (
    <div className="space-y-0.5 text-xs">
      <div className="font-mono">
        Average {rupees(history.mean)}, won {Math.round((history.win_rate ?? 0) * 100)}%
      </div>
      <div className="font-mono text-muted-foreground">
        Worst {rupees(history.worst)}, {history.trades} weeks
      </div>
      <div className="font-mono text-muted-foreground">
        Older {rupees(history.older_mean)}, recent {rupees(history.recent_mean)}
      </div>
      {bucket?.trades ? (
        <div className="font-mono">
          With VIX like today ({bucket.bucket}): {rupees(bucket.mean)}, won{' '}
          {Math.round((bucket.win_rate ?? 0) * 100)}%, {bucket.trades} weeks
        </div>
      ) : (
        <div className="text-muted-foreground">{bucket?.note}</div>
      )}
      {history.note && <div className="text-amber-600">{history.note}</div>}
    </div>
  )
}

function Scenarios({ row }: { row: PickerRow }) {
  if (!row.scenarios) return <span className="text-xs text-muted-foreground">-</span>
  return (
    <div className="space-y-0.5 font-mono text-xs">
      {row.scenarios.map((s) => (
        <div key={s.multiple} className="flex justify-between gap-3">
          <span className="text-muted-foreground">
            {s.multiple === 0 ? 'Flat' : `${s.multiple > 0 ? '+' : ''}${s.multiple} move`} (
            {Math.round(s.nifty).toLocaleString('en-IN')})
          </span>
          <span className={s.pnl >= 0 ? 'text-green-600' : 'text-red-500'}>{rupees(s.pnl)}</span>
        </div>
      ))}
    </div>
  )
}

function Row({
  row,
  blocked,
  onTrack,
  tracking,
}: {
  row: PickerRow
  blocked: boolean
  onTrack?: (id: string) => void
  tracking?: string | null
}) {
  const stats = row.stats
  const credit = stats?.net_credit ?? 0
  return (
    <tr className="border-b align-top">
      <td className="py-2 pr-3 font-medium">
        {row.name}
        <div className="max-w-[260px] text-xs font-normal text-muted-foreground">
          {row.evidence}
        </div>
        {blocked &&
          row.blocked_because.map((reason) => (
            <div key={reason} className="max-w-[260px] text-xs font-normal text-red-500">
              {reason}
            </div>
          ))}
      </td>
      <td className="py-2 pr-3 text-right font-mono">{blocked ? '-' : row.score?.toFixed(0)}</td>
      <td className="py-2 pr-3 text-right font-mono text-green-600">
        {stats ? (stats.max_profit === null ? 'Unlimited' : rupees(stats.max_profit)) : '-'}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-red-500">
        {stats ? (stats.unbounded_loss ? 'Unlimited' : rupees(stats.max_loss)) : '-'}
      </td>
      <td className="py-2 pr-3 text-right font-mono">
        {rupees(row.capital_required)}
        <div className="text-xs text-muted-foreground">{row.capital_source}</div>
      </td>
      <td className="py-2 pr-3 text-right font-mono">
        {stats ? `${credit >= 0 ? 'Credit' : 'Debit'} ${rupees(Math.abs(credit))}` : '-'}
      </td>
      <td className="py-2 pr-3 text-right font-mono">
        {stats?.breakevens.length ? stats.breakevens.map((b) => Math.round(b)).join(', ') : '-'}
      </td>
      <td className="py-2 pr-3 text-right font-mono">{rupees(row.costs?.total)}</td>
      <td className="min-w-[170px] py-2 pr-3">
        <Scenarios row={row} />
      </td>
      <td className="min-w-[210px] py-2 pr-3">
        <PastWeeks history={row.history} />
      </td>
      <td className="py-2">
        {!blocked && onTrack ? (
          <Button
            variant="outline"
            size="sm"
            disabled={tracking === row.id}
            onClick={() => onTrack(row.id)}
            aria-label={`Track ${row.name}`}
          >
            Track
          </Button>
        ) : null}
      </td>
    </tr>
  )
}

function Table({
  rows,
  blocked,
  onTrack,
  tracking,
}: {
  rows: PickerRow[]
  blocked: boolean
  onTrack?: (id: string) => void
  tracking?: string | null
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="py-2 pr-3">Strategy</th>
            <th className="py-2 pr-3 text-right">Fit</th>
            <th className="py-2 pr-3 text-right">Most it can earn</th>
            <th className="py-2 pr-3 text-right">Most it can lose</th>
            <th className="py-2 pr-3 text-right">Capital needed</th>
            <th className="py-2 pr-3 text-right">Entry</th>
            <th className="py-2 pr-3 text-right">Breakevens</th>
            <th className="py-2 pr-3 text-right">Costs, in and out</th>
            <th className="py-2 pr-3">If Nifty ends here at expiry</th>
            <th className="py-2 pr-3">Past weeks of the same structure</th>
            <th className="py-2">Follow it</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <Row key={row.id} row={row} blocked={blocked} onTrack={onTrack} tracking={tracking} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export type PickerSort = 'fit' | 'max_profit' | 'max_loss' | 'capital' | 'costs' | 'history'

export type PickerViewSettings = {
  definedRiskOnly: boolean
  maxLossLimit: number | null
  capitalLimit: number | null
  costsLimit: number | null
  sort: PickerSort
}

export const PICKER_VIEW_DEFAULTS: PickerViewSettings = {
  definedRiskOnly: false,
  maxLossLimit: null,
  capitalLimit: null,
  costsLimit: null,
  sort: 'fit',
}

const SORT_DIRECTION: Record<PickerSort, 1 | -1> = {
  fit: -1,
  max_profit: -1,
  max_loss: 1,
  capital: 1,
  costs: 1,
  history: -1,
}

// The value a row is ordered by. Null means there is nothing to order by, and
// such rows sort last whichever way the order runs.
function sortValue(row: PickerRow, sort: PickerSort): number | null {
  const stats = row.stats
  switch (sort) {
    case 'fit':
      return row.score ?? null
    case 'max_profit':
      return stats ? (stats.max_profit ?? Number.POSITIVE_INFINITY) : null
    case 'max_loss':
      return stats
        ? stats.unbounded_loss || stats.max_loss === null
          ? Number.POSITIVE_INFINITY
          : stats.max_loss
        : null
    case 'capital':
      return row.capital_required ?? null
    case 'costs':
      return row.costs?.total ?? null
    case 'history':
      return row.history?.available ? (row.history.mean ?? null) : null
  }
}

function compareMissingLast(a: number | null, b: number | null, direction: 1 | -1): number {
  if (a === b) return 0
  if (a === null) return 1
  if (b === null) return -1
  return (a - b) * direction
}

export function isDefaultPickerView(view: PickerViewSettings): boolean {
  return (
    view.definedRiskOnly === PICKER_VIEW_DEFAULTS.definedRiskOnly &&
    view.maxLossLimit === PICKER_VIEW_DEFAULTS.maxLossLimit &&
    view.capitalLimit === PICKER_VIEW_DEFAULTS.capitalLimit &&
    view.costsLimit === PICKER_VIEW_DEFAULTS.costsLimit &&
    view.sort === PICKER_VIEW_DEFAULTS.sort
  )
}

/**
 * Filters and orders the rows of the "Within your limits" table. Returns a new
 * array; the input is not changed. The sort is stable, so rows that tie keep the
 * order the picker gave them.
 */
export function applyPickerView(rows: PickerRow[], view: PickerViewSettings): PickerRow[] {
  const kept = rows.filter((row) => {
    if (view.definedRiskOnly && !(row.stats && !row.stats.unbounded_loss)) return false
    if (
      view.maxLossLimit !== null &&
      !(row.stats?.max_loss != null && row.stats.max_loss <= view.maxLossLimit)
    ) {
      return false
    }
    if (
      view.capitalLimit !== null &&
      !(row.capital_required != null && row.capital_required <= view.capitalLimit)
    ) {
      return false
    }
    if (view.costsLimit !== null && !(row.costs && row.costs.total <= view.costsLimit)) {
      return false
    }
    return true
  })
  const direction = SORT_DIRECTION[view.sort]
  return kept.sort((a, b) =>
    compareMissingLast(sortValue(a, view.sort), sortValue(b, view.sort), direction)
  )
}

const MAX_LOSS_OPTIONS = [2000, 5000, 10000, 20000]
const CAPITAL_OPTIONS = [25000, 50000, 100000]
const COSTS_OPTIONS = [150, 300, 600]
const SORT_OPTIONS: { value: PickerSort; label: string }[] = [
  { value: 'fit', label: 'Fit, highest first' },
  { value: 'max_profit', label: 'Most it can earn' },
  { value: 'max_loss', label: 'Least it can lose' },
  { value: 'capital', label: 'Least capital needed' },
  { value: 'costs', label: 'Lowest costs' },
  { value: 'history', label: 'Best past average' },
]
const selectClass = 'h-8 rounded-md border bg-background px-2 text-sm'

function LimitSelect({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string
  label: string
  value: number | null
  options: number[]
  onChange: (value: number | null) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </label>
      <select
        id={id}
        className={selectClass}
        value={value === null ? 'any' : String(value)}
        onChange={(event) =>
          onChange(event.target.value === 'any' ? null : Number(event.target.value))
        }
      >
        <option value="any">Any</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {rupees(option)}
          </option>
        ))}
      </select>
    </div>
  )
}

function PickerFilters({
  view,
  onChange,
  onReset,
  shown,
  total,
}: {
  view: PickerViewSettings
  onChange: (next: PickerViewSettings) => void
  onReset: () => void
  shown: number
  total: number
}) {
  return (
    <div className="flex flex-wrap items-end gap-x-4 gap-y-3 border-b pb-3">
      <label className="flex h-8 items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border bg-background"
          checked={view.definedRiskOnly}
          onChange={(event) => onChange({ ...view, definedRiskOnly: event.target.checked })}
        />
        Defined risk only
      </label>
      <LimitSelect
        id="picker-max-loss"
        label="Most it can lose, up to"
        value={view.maxLossLimit}
        options={MAX_LOSS_OPTIONS}
        onChange={(maxLossLimit) => onChange({ ...view, maxLossLimit })}
      />
      <LimitSelect
        id="picker-capital"
        label="Capital needed, up to"
        value={view.capitalLimit}
        options={CAPITAL_OPTIONS}
        onChange={(capitalLimit) => onChange({ ...view, capitalLimit })}
      />
      <LimitSelect
        id="picker-costs"
        label="Costs, in and out, up to"
        value={view.costsLimit}
        options={COSTS_OPTIONS}
        onChange={(costsLimit) => onChange({ ...view, costsLimit })}
      />
      <div className="flex flex-col gap-1">
        <label htmlFor="picker-sort" className="text-xs text-muted-foreground">
          Sort by
        </label>
        <select
          id="picker-sort"
          className={selectClass}
          value={view.sort}
          onChange={(event) => onChange({ ...view, sort: event.target.value as PickerSort })}
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          Showing {shown} of {total}
        </span>
        <Button variant="ghost" size="sm" onClick={onReset} disabled={isDefaultPickerView(view)}>
          Reset
        </Button>
      </div>
    </div>
  )
}

export function PickerPanel() {
  const [withMargins, setWithMargins] = useState(false)
  const [view, setView] = useState<PickerViewSettings>(PICKER_VIEW_DEFAULTS)
  const [tracking, setTracking] = useState<string | null>(null)
  const queryClient = useQueryClient()

  async function track(id: string) {
    setTracking(id)
    try {
      await trackPick(id)
      showToast.success('Tracked. Follow it under My picks. No order was placed.', 'system')
      await queryClient.invalidateQueries({ queryKey: algoQueryKeys.picks() })
    } catch (error) {
      const message = (error as { response?: { data?: { message?: string } } })?.response?.data
        ?.message
      showToast.error(message || 'Could not track this strategy. Refresh the picker.', 'system')
    } finally {
      setTracking(null)
    }
  }
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: algoQueryKeys.picker(withMargins),
    queryFn: () => fetchPicker(withMargins),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 45_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {withMargins
          ? 'Asking the broker for margins. This can take up to 15 seconds.'
          : 'Pricing every structure from the live chain.'}
      </div>
    )
  }
  if (isError || !data) {
    return <p className="text-sm text-red-500">{errorText(error)}</p>
  }
  const h = data.header
  const visibleRanked = applyPickerView(data.ranked, view)
  const gap = h.research?.expected_gap
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div>
              <CardTitle>Strategy picker</CardTitle>
              <CardDescription>
                Every structure priced live: what it can earn and lose, the capital it needs, how
                well today suits it, and how the same structure did in past weeks. You choose.
                Nothing here places an order.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              {!withMargins && (
                <Button variant="outline" size="sm" onClick={() => setWithMargins(true)}>
                  Get broker margins
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
                <RefreshCw className={`mr-1 h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} /> Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">Nifty {h.spot.toLocaleString('en-IN')}</Badge>
            <Badge variant="outline">
              Expiry {h.expiry} ({h.dte} days)
            </Badge>
            <Badge variant="outline">Lot {h.lot}</Badge>
            {h.vix ? <Badge variant="outline">India VIX {h.vix.toFixed(1)}</Badge> : null}
            {h.regime ? (
              <Badge variant="outline">
                {h.regime.label}, {h.regime.bias}
              </Badge>
            ) : null}
            {h.expected_move.fifteen_minutes ? (
              <Badge variant="outline">
                Typical 15-minute move {h.expected_move.fifteen_minutes} points
              </Badge>
            ) : null}
            <Badge variant="outline">
              Your limits: capital {rupees(h.capital)}, daily loss {rupees(h.daily_cap)}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">{h.disclaimer}</p>
          {h.history_note && <p className="text-xs text-muted-foreground">{h.history_note}</p>}
          <p className="text-xs text-muted-foreground">
            Earn and loss figures are for one lot held to expiry. Capital needed is the broker's
            margin ({h.margins_from_broker ?? 0} structures; press Get broker margins) or else the
            premium paid. Costs are the charges plus the gap between buy and sell prices for getting
            in and out once. The scenario column shows your result after costs if Nifty ends expiry
            one or two typical moves (for the days left, from India VIX) up or down. It is a
            what-if, not a forecast.
          </p>
          {h.research && (
            <div className="rounded-md border p-2 text-xs">
              <div className="font-medium">What the research data says</div>
              {gap?.gap_pct !== null && gap?.gap_pct !== undefined ? (
                <p>
                  Overseas markets today point to a Nifty opening gap of about{' '}
                  {gap.gap_pct >= 0 ? '+' : ''}
                  {gap.gap_pct.toFixed(2)} percent (
                  {gap.links
                    .map((l) => `${l.label} ${l.move_pct >= 0 ? '+' : ''}${l.move_pct.toFixed(2)}%`)
                    .join(', ')}
                  ). A rough estimate from links that held on years the study had not seen.
                </p>
              ) : (
                <p>No overseas moves were available, so there is no gap estimate.</p>
              )}
              {Object.entries(h.research.skill).map(([key, item]) => (
                <p key={key} className={item.usable ? '' : 'text-muted-foreground'}>
                  {item.note}
                </p>
              ))}
              <p className="text-muted-foreground">
                So the picker lets direction matter only before the open. After it, direction counts
                for little, and volatility, cost and your limits do most of the work.
              </p>
            </div>
          )}
          {h.notes.map((note) => (
            <p key={note} className="text-xs text-amber-600">
              {note}
            </p>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Within your limits ({data.ranked.length})</CardTitle>
          <CardDescription>
            Highest fit first. Fit is not a forecast of profit, and past weeks are not a promise.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <PickerFilters
            view={view}
            onChange={setView}
            onReset={() => setView(PICKER_VIEW_DEFAULTS)}
            shown={visibleRanked.length}
            total={data.ranked.length}
          />
          {visibleRanked.length === 0 && data.ranked.length > 0 ? (
            <p className="py-6 text-sm text-muted-foreground">
              No strategy matches these filters. Loosen one of them or press Reset.
            </p>
          ) : (
            <Table rows={visibleRanked} blocked={false} onTrack={track} tracking={tracking} />
          )}
        </CardContent>
      </Card>
      {data.blocked.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Outside your limits ({data.blocked.length})</CardTitle>
            <CardDescription>
              Shown so you can see why; the reason is under each name.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table rows={data.blocked} blocked />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
