import { useState } from 'react'
import { hm } from '../format'
import { TipBox, useWidth, type Tip } from './common'

const H = 40
const STATUS_COLOR: Record<string, string> = {
  OUTAGE: 'var(--critical)',
  SOURCE_ERROR: 'var(--serious)',
}
const STATUS_TEXT: Record<string, string> = {
  OK: 'норма',
  OUTAGE: 'сбой',
  SOURCE_ERROR: 'не ответил',
  DISABLED: 'отключён',
}

/** 24 h of one site: complaints line if the site gives numbers, and a strip marking
 *  checks that saw an outage (red) or got no answer (orange). */
export default function Sparkline({ points }: { points: [string, number | null, string][] }) {
  const { ref, width } = useWidth<HTMLDivElement>(240)
  const [tip, setTip] = useState<Tip | null>(null)
  const now = Date.now()
  const from = now - 24 * 3600_000
  const sx = (ts: string) => ((new Date(ts).getTime() - from) / (now - from)) * width
  const counts = points.filter((p) => p[1] !== null) as [string, number, string][]
  const max = Math.max(1, ...counts.map((p) => p[1]))
  const lineH = H - 8
  const sy = (v: number) => 2 + (lineH - 4) * (1 - v / max)

  const onMove = (clientX: number, left: number) => {
    if (!points.length) return
    const target = from + ((clientX - left) / width) * (now - from)
    const p = points.reduce((best, q) =>
      Math.abs(new Date(q[0]).getTime() - target) < Math.abs(new Date(best[0]).getTime() - target) ? q : best)
    setTip({
      x: sx(p[0]),
      y: 0,
      content: (
        <>
          <span className="muted">{hm(p[0])}</span>{' '}
          {p[1] !== null && <strong>{p[1]} в час · </strong>}
          {STATUS_TEXT[p[2]] ?? p[2]}
        </>
      ),
    })
  }

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={H} role="img" aria-label="Последние сутки">
        {counts.length > 1 && (
          <path
            d={counts.map((p, i) => `${i ? 'L' : 'M'}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join('')}
            fill="none" stroke="var(--s1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
          />
        )}
        <line x1={0} x2={width} y1={H - 3} y2={H - 3} stroke="var(--grid)" strokeWidth={4} strokeLinecap="round" />
        {points.filter((p) => STATUS_COLOR[p[2]]).map((p) => (
          <rect key={p[0]} x={sx(p[0]) - 1.5} y={H - 5} width={3} height={4} rx={1} fill={STATUS_COLOR[p[2]]} />
        ))}
        <rect x={0} y={0} width={width} height={H} fill="transparent"
              onMouseMove={(e) => onMove(e.clientX, e.currentTarget.getBoundingClientRect().left)}
              onMouseLeave={() => setTip(null)} />
      </svg>
      <TipBox tip={tip} />
    </div>
  )
}
