import { cn } from '@/lib/utils'

interface Props {
  curve: [string, number][]
  className?: string
}

const W = 640
const H = 180
const PAD = { left: 8, right: 8, top: 10, bottom: 18 }

/** Running total per lot as a line, with the zero line drawn so a loss is visible as one. */
export function EquityCurve({ curve, className }: Props) {
  if (curve.length < 2) {
    return <p className="text-sm text-muted-foreground">Too few trades to draw a curve.</p>
  }
  const values = curve.map(([, v]) => v)
  const lo = Math.min(0, ...values)
  const hi = Math.max(0, ...values)
  const span = hi - lo || 1
  const x = (i: number) => PAD.left + (i / (curve.length - 1)) * (W - PAD.left - PAD.right)
  const y = (v: number) => PAD.top + (1 - (v - lo) / span) * (H - PAD.top - PAD.bottom)
  const points = curve.map(([, v], i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const last = values[values.length - 1]
  const first = curve[0][0]
  const end = curve[curve.length - 1][0]
  const label = `Running result per lot from ${first} to ${end}, ending at ${Math.round(last).toLocaleString('en-IN')} rupees`

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={label}
      className={cn('h-auto w-full', className)}
    >
      <title>{label}</title>
      <line
        x1={PAD.left}
        x2={W - PAD.right}
        y1={y(0)}
        y2={y(0)}
        className="stroke-muted-foreground/40"
        strokeDasharray="4 4"
      />
      <polyline
        points={points}
        fill="none"
        strokeWidth={2}
        className={last >= 0 ? 'stroke-emerald-500' : 'stroke-red-500'}
      />
      <text x={PAD.left} y={H - 4} className="fill-muted-foreground text-[10px]">
        {first}
      </text>
      <text
        x={W - PAD.right}
        y={H - 4}
        textAnchor="end"
        className="fill-muted-foreground text-[10px]"
      >
        {end}
      </text>
    </svg>
  )
}
