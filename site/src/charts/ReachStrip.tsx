import { useState } from 'react'
import { hm, reachIcon } from '../format'
import { TipBox, useWidth, type Tip } from './common'

const H = 14

/** 24 h of one site from one region: a tick per check, green when every point answered,
 *  amber when some did, red when none did. Status colors always come with an icon in the tip. */
function color(up: number, total: number): string {
  return up === total ? 'var(--good)' : up === 0 ? 'var(--critical)' : 'var(--warning)'
}

export default function ReachStrip({ points, label }: { points: [string, number, number][]; label: string }) {
  const { ref, width } = useWidth<HTMLDivElement>(240)
  const [tip, setTip] = useState<Tip | null>(null)
  const now = Date.now()
  const from = now - 24 * 3600_000
  const sx = (ts: string) => ((new Date(ts).getTime() - from) / (now - from)) * width
  // a check covers its 5 minutes; at least 2px so single ticks stay visible
  const w = Math.max(2, (width * 5) / (24 * 60) - 0.5)

  const onMove = (clientX: number, left: number) => {
    if (!points.length) return
    const target = from + ((clientX - left) / width) * (now - from)
    const p = points.reduce((best, q) =>
      Math.abs(new Date(q[0]).getTime() - target) < Math.abs(new Date(best[0]).getTime() - target) ? q : best)
    setTip({
      x: sx(p[0]),
      y: 0,
      content: <><span className="muted">{hm(p[0])}</span> {reachIcon(p[1], p[2])} {p[1]} из {p[2]}</>,
    })
  }

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={H} role="img" aria-label={`${label}: последние сутки`}>
        <rect x={0} y={4} width={width} height={H - 8} rx={2} fill="var(--grid)" />
        {points.map((p) => (
          <rect key={p[0]} x={sx(p[0]) - w} y={1} width={w} height={H - 2} rx={1} fill={color(p[1], p[2])} />
        ))}
        <rect x={0} y={0} width={width} height={H} fill="transparent"
              onMouseMove={(e) => onMove(e.clientX, e.currentTarget.getBoundingClientRect().left)}
              onMouseLeave={() => setTip(null)} />
      </svg>
      <TipBox tip={tip} />
    </div>
  )
}
