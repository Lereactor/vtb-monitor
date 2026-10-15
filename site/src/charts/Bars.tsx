import { useState, type ReactNode } from 'react'
import { compact, ticks, TipBox, useWidth, type Tip } from './common'

export interface Bar {
  label: string // x-axis label
  value: number
  tip: ReactNode
}

const H = 180
const PAD = { top: 16, right: 8, bottom: 24, left: 32 }

/** Columns from one baseline: ≤24px thick, 4px rounded top, 2px surface gap, per-bar tooltip. */
export default function Bars({ bars, color = 'var(--s1)' }: { bars: Bar[]; color?: string }) {
  const { ref, width } = useWidth<HTMLDivElement>()
  const [tip, setTip] = useState<Tip | null>(null)
  if (!bars.length) return <div className="empty">Нет данных за период</div>
  const yTicks = ticks(Math.max(1, ...bars.map((b) => b.value)))
  const top = yTicks[yTicks.length - 1]
  const plotW = width - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const slot = plotW / bars.length
  const barW = Math.max(2, Math.min(24, slot - 2))
  const sy = (v: number) => PAD.top + plotH - (v / top) * plotH
  const labelEvery = Math.ceil(bars.length / Math.max(1, Math.floor(plotW / 48)))
  const max = Math.max(...bars.map((b) => b.value))

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={H} role="img" aria-label="Сбои по дням">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={sy(t)} y2={sy(t)} stroke="var(--grid)" />
            <text x={PAD.left - 6} y={sy(t) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">
              {compact(t)}
            </text>
          </g>
        ))}
        {bars.map((b, i) => {
          const cx = PAD.left + slot * i + slot / 2
          const h = Math.max(0, sy(0) - sy(b.value))
          const x = cx - barW / 2
          const y = sy(b.value)
          const r = Math.min(4, barW / 2, h)
          const path = h
            ? `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + barW - r}Q${x + barW},${y} ${x + barW},${y + r}V${y + h}Z`
            : ''
          return (
            <g key={b.label + i}>
              {path && <path d={path} fill={color} />}
              {b.value > 0 && b.value === max && (
                <text x={cx} y={y - 4} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{b.value}</text>
              )}
              {i % labelEvery === 0 && (
                <text x={cx} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--muted)">{b.label}</text>
              )}
              <rect x={PAD.left + slot * i} y={PAD.top} width={slot} height={plotH} fill="transparent"
                    onMouseEnter={() => setTip({ x: cx, y: Math.min(y, sy(0) - 8), content: b.tip })}
                    onMouseLeave={() => setTip(null)} />
            </g>
          )
        })}
        <line x1={PAD.left} x2={width - PAD.right} y1={sy(0)} y2={sy(0)} stroke="var(--axis)" />
      </svg>
      <TipBox tip={tip} />
    </div>
  )
}
