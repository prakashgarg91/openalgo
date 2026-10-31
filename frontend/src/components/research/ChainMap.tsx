import { useMemo } from 'react'
import type { DominoChain } from '@/api/research'
import { cn } from '@/lib/utils'

const WIDTH = 900
const ROW = 27
const X_LEFT = 215
const X_MID = 450
const X_RIGHT = 690
const TOP = 24

interface Props {
  chains: DominoChain[]
  selected: string | null
  onSelect: (id: string | null) => void
}

interface Col {
  id: string
  label: string
  y: number
}

function column(entries: [string, string][], gap = 0): Col[] {
  return entries.map(([id, label], i) => ({ id, label, y: TOP + i * ROW + gap }))
}

function colorFor(beta: number): string {
  return beta >= 0 ? '#10b981' : '#f43f5e'
}

function curve(x1: number, y1: number, x2: number, y2: number): string {
  const mid = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`
}

export function ChainMap({ chains, selected, onSelect }: Props) {
  const layout = useMemo(() => {
    const drivers = new Map<string, string>()
    const middles = new Map<string, { label: string; n: number }>()
    const ends = new Map<string, string>()
    for (const c of chains) {
      drivers.set(c.driver, c.driver_label)
      ends.set(c.end, c.end_label)
      const m = middles.get(c.middle)
      middles.set(c.middle, { label: c.middle_label, n: (m?.n ?? 0) + 1 })
    }
    const left = column(
      [...drivers.entries()].sort((a, b) => a[1].localeCompare(b[1])) as [string, string][]
    )
    const sortedMid = [...middles.entries()].sort((a, b) => b[1].n - a[1].n)
    const total = Math.max(left.length, sortedMid.length * 3, 4)
    const step = (total * ROW) / Math.max(sortedMid.length, 1)
    const mid: Col[] = sortedMid.map(([id, v], i) => ({
      id,
      label: v.label,
      y: TOP + i * step + step / 2 - ROW / 2,
    }))
    const endList = [...ends.entries()]
    const estep = (total * ROW) / Math.max(endList.length, 1)
    const right: Col[] = endList.map(([id, label], i) => ({
      id,
      label,
      y: TOP + i * estep + estep / 2 - ROW / 2,
    }))
    const stage1 = new Map<string, DominoChain>()
    const stage2 = new Map<string, DominoChain>()
    for (const c of chains) {
      stage1.set(`${c.driver}|${c.middle}`, c)
      stage2.set(`${c.middle}|${c.end}`, c)
    }
    return { left, mid, right, stage1: [...stage1.values()], stage2: [...stage2.values()], total }
  }, [chains])

  const at = (cols: Col[], id: string) => cols.find((c) => c.id === id)
  const height = TOP * 2 + layout.total * ROW
  const hit = (c: DominoChain) =>
    !selected || c.driver === selected || c.middle === selected || c.end === selected

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      className="mx-auto h-auto w-full max-w-[900px]"
      role="img"
      aria-label="Chains from a foreign market through a sector or stock to the Nifty"
    >
      <title>Chains from a foreign market through a sector or stock to the Nifty</title>
      {[
        [X_LEFT, 'Foreign market'],
        [X_MID, 'Sector or stock opening gap'],
        [X_RIGHT, 'What the Nifty does'],
      ].map(([x, label]) => (
        <text
          key={label as string}
          x={x as number}
          y={10}
          textAnchor="middle"
          className="fill-muted-foreground text-[11px] font-medium"
        >
          {label}
        </text>
      ))}
      {layout.stage1.map((c) => {
        const a = at(layout.left, c.driver)
        const b = at(layout.mid, c.middle)
        if (!a || !b) return null
        return (
          <path
            key={`${c.driver}-${c.middle}`}
            d={curve(X_LEFT + 6, a.y, X_MID - 6, b.y)}
            fill="none"
            stroke={colorFor(c.stage1_beta)}
            strokeWidth={Math.min(3.2, 0.6 + Math.abs(c.stage1_t) / 3)}
            opacity={hit(c) ? (selected ? 0.9 : 0.5) : 0.06}
            strokeLinecap="round"
          />
        )
      })}
      {layout.stage2.map((c) => {
        const a = at(layout.mid, c.middle)
        const b = at(layout.right, c.end)
        if (!a || !b) return null
        return (
          <path
            key={`${c.middle}-${c.end}`}
            d={curve(X_MID + 6, a.y, X_RIGHT - 6, b.y)}
            fill="none"
            stroke={colorFor(c.stage2_beta)}
            strokeWidth={Math.min(4, 0.8 + Math.abs(c.stage2_t) / 1.5)}
            opacity={hit(c) ? (selected ? 0.95 : 0.7) : 0.06}
            strokeLinecap="round"
          />
        )
      })}
      {[
        { cols: layout.left, x: X_LEFT, side: 'left' as const },
        { cols: layout.mid, x: X_MID, side: 'mid' as const },
        { cols: layout.right, x: X_RIGHT, side: 'right' as const },
      ].flatMap(({ cols, x, side }) =>
        cols.map((c) => {
          const isSel = selected === c.id
          return (
            <g
              key={`${side}-${c.id}`}
              className="cursor-pointer"
              onClick={() => onSelect(isSel ? null : c.id)}
            >
              <circle
                cx={x}
                cy={c.y}
                r={isSel ? 7 : 5.5}
                className={cn(
                  'stroke-background',
                  side === 'mid'
                    ? 'fill-amber-500'
                    : side === 'right'
                      ? 'fill-primary'
                      : 'fill-indigo-500'
                )}
                strokeWidth={1.5}
              />
              <text
                x={side === 'left' ? x - 12 : x + 12}
                y={c.y}
                textAnchor={side === 'left' ? 'end' : 'start'}
                dominantBaseline="middle"
                className={cn(
                  'select-none fill-muted-foreground text-[11.5px]',
                  isSel && 'fill-foreground font-semibold'
                )}
              >
                {c.label}
              </text>
              <rect x={x - 14} y={c.y - 12} width={28} height={24} fill="transparent" />
            </g>
          )
        })
      )}
    </svg>
  )
}
