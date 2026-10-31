import { useMemo } from 'react'
import type { LinkageData, LinkStatus, ResearchLink, ResearchNode } from '@/api/research'
import { cn } from '@/lib/utils'

export const GROUP_COLOR: Record<string, string> = {
  us_risk: '#6366f1',
  us_futures: '#8b5cf6',
  fx: '#0ea5e9',
  commodities: '#f59e0b',
  asia: '#ec4899',
  europe: '#14b8a6',
  overseas_india_etfs: '#84cc16',
  india_indices: '#f97316',
  india_heavyweights: '#ef4444',
  baseline: '#64748b',
}

const SIZE = 860
const CENTER = SIZE / 2
const RING = 262
const TARGET_OFFSET = 74

interface Props {
  data: LinkageData
  activeTargets: Set<string>
  mode: 'held' | 'all'
  selected: string | null
  onSelect: (id: string | null) => void
}

interface Placed {
  node: ResearchNode
  x: number
  y: number
  angle: number
}

export function statusLabel(status: LinkStatus): string {
  switch (status) {
    case 'verified':
      return 'Held up'
    case 'weak':
      return 'Same direction, weaker'
    case 'flipped':
      return 'Reversed'
    default:
      return 'No link found'
  }
}

function strokeFor(link: ResearchLink): { color: string; width: number; dash?: string } {
  if (link.status === 'verified') {
    const width = Math.min(3.6, 0.7 + Math.abs(link.t_ver ?? 0) / 4)
    return { color: (link.beta_ver ?? 0) >= 0 ? '#10b981' : '#f43f5e', width }
  }
  if (link.status === 'flipped') return { color: '#f59e0b', width: 1, dash: '4 3' }
  return { color: '#94a3b8', width: 0.9, dash: '2 3' }
}

export function LinkageMap({ data, activeTargets, mode, selected, onSelect }: Props) {
  const linked = useMemo(() => {
    const ids = new Set<string>()
    for (const l of data.links) if (l.status !== 'not_selected') ids.add(l.source)
    return ids
  }, [data.links])

  const { drivers, targets } = useMemo(() => {
    const order = data.groups.map((g) => g.id)
    const list = data.nodes
      .filter((n) => n.kind === 'driver' && linked.has(n.id))
      .sort(
        (a, b) => order.indexOf(a.group) - order.indexOf(b.group) || a.label.localeCompare(b.label)
      )
    const gaps = new Set<number>()
    list.forEach((n, i) => {
      if (i > 0 && list[i - 1].group !== n.group) gaps.add(i)
    })
    const unit = (Math.PI * 2) / (list.length + gaps.size * 1.4)
    let a = -Math.PI / 2
    const placed: Placed[] = list.map((node, i) => {
      if (gaps.has(i)) a += unit * 1.4
      const p = { node, x: CENTER + RING * Math.cos(a), y: CENTER + RING * Math.sin(a), angle: a }
      a += unit
      return p
    })
    const corners = [
      [-1, -1],
      [1, -1],
      [-1, 1],
      [1, 1],
    ]
    const tg = data.nodes
      .filter((n) => n.kind === 'target')
      .map((node, i) => ({
        node,
        x: CENTER + corners[i][0] * TARGET_OFFSET,
        y: CENTER + corners[i][1] * TARGET_OFFSET,
        angle: 0,
      }))
    return { drivers: placed, targets: tg }
  }, [data.nodes, data.groups, linked])

  const byId = useMemo(() => {
    const m = new Map<string, Placed>()
    for (const p of [...drivers, ...targets]) m.set(p.node.id, p)
    return m
  }, [drivers, targets])

  const edges = data.links.filter(
    (l) =>
      l.status !== 'not_selected' &&
      activeTargets.has(l.target) &&
      (mode === 'all' || l.status === 'verified') &&
      byId.has(l.source)
  )

  const focused = (l: ResearchLink) => !selected || l.source === selected || l.target === selected

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="mx-auto h-auto w-full max-w-[860px]"
      role="img"
      aria-label="Map of foreign markets, sectors and stocks that move with the Nifty"
    >
      <title>Map of markets that move with the Nifty</title>
      <circle
        cx={CENTER}
        cy={CENTER}
        r={RING}
        className="fill-none stroke-border"
        strokeDasharray="2 6"
      />
      {edges.map((l) => {
        const s = byId.get(l.source)
        const t = byId.get(l.target)
        if (!s || !t) return null
        const st = strokeFor(l)
        const cx = CENTER + (s.x - CENTER) * 0.28
        const cy = CENTER + (s.y - CENTER) * 0.28
        return (
          <path
            key={`${l.source}-${l.target}`}
            d={`M ${s.x} ${s.y} Q ${cx} ${cy} ${t.x} ${t.y}`}
            fill="none"
            stroke={st.color}
            strokeWidth={st.width}
            strokeDasharray={st.dash}
            strokeLinecap="round"
            opacity={focused(l) ? (selected ? 0.95 : 0.55) : 0.05}
          />
        )
      })}
      {drivers.map(({ node, x, y, angle }) => {
        const right = Math.cos(angle) >= 0
        const deg = (angle * 180) / Math.PI
        const isSel = selected === node.id
        const dim = selected && !isSel && !edges.some((e) => e.source === node.id && focused(e))
        return (
          <g
            key={node.id}
            className="cursor-pointer"
            opacity={dim ? 0.35 : 1}
            onClick={() => onSelect(isSel ? null : node.id)}
          >
            <circle
              cx={x}
              cy={y}
              r={isSel ? 7.5 : 5.5}
              fill={GROUP_COLOR[node.group] ?? '#64748b'}
              className="stroke-background"
              strokeWidth={1.5}
            />
            <text
              transform={`translate(${x} ${y}) rotate(${right ? deg : deg + 180}) translate(${right ? 11 : -11} 0)`}
              textAnchor={right ? 'start' : 'end'}
              dominantBaseline="middle"
              className={cn(
                'select-none fill-muted-foreground text-[10.5px]',
                isSel && 'fill-foreground font-semibold'
              )}
            >
              {node.label}
            </text>
            <circle cx={x} cy={y} r={14} fill="transparent" />
          </g>
        )
      })}
      {targets.map(({ node, x, y }) => {
        const on = activeTargets.has(node.id)
        return (
          <g
            key={node.id}
            className="cursor-pointer"
            opacity={on ? 1 : 0.4}
            onClick={() => onSelect(selected === node.id ? null : node.id)}
          >
            <circle
              cx={x}
              cy={y}
              r={selected === node.id ? 30 : 27}
              className="fill-primary stroke-background"
              strokeWidth={2}
            />
            {node.label
              .split(' ')
              .reduce<string[]>((lines, word) => {
                const last = lines[lines.length - 1]
                if (last && (last + ' ' + word).length <= 9)
                  lines[lines.length - 1] = `${last} ${word}`
                else lines.push(word)
                return lines
              }, [])
              .map((line, i, arr) => (
                <text
                  key={line}
                  x={x}
                  y={y + (i - (arr.length - 1) / 2) * 10.5}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="select-none fill-primary-foreground text-[9.5px] font-medium"
                >
                  {line}
                </text>
              ))}
          </g>
        )
      })}
    </svg>
  )
}
