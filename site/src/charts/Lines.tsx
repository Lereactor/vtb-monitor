import { useState, type MouseEvent } from 'react'
import { compact, ticks, TipBox, useWidth, type Tip } from './common'

export interface Series {
  key: string
  label: string
  color: string
  points: [number, number][] // x = epoch ms, y = value
}

const H = 220
const PAD = { top: 12, right: 12, bottom: 24, left: 36 }

/** Line chart: 2px lines, legend for 2+ series, crosshair + one tooltip listing every series. */
export default function Lines({ series, formatX, height = H }: {
  series: Series[]
  formatX: (x: number) => string
  height?: number
}) {
  const { ref, width } = useWidth<HTMLDivElement>()
  const [tip, setTip] = useState<Tip | null>(null)
  const [hoverX, setHoverX] = useState<number | null>(null)
  const xs = series.flatMap((s) => s.points.map((p) => p[0]))
  if (!xs.length) return <div className="empty">Нет данных за период</div>
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs, minX + 1)
  const maxY = Math.max(1, ...series.flatMap((s) => s.points.map((p) => p[1])))
  const yTicks = ticks(maxY)
  const top = yTicks[yTicks.length - 1]
  const plotW = width - PAD.left - PAD.right
  const plotH = height - PAD.top - PAD.bottom
  const sx = (x: number) => PAD.left + ((x - minX) / (maxX - minX)) * plotW
  const sy = (y: number) => PAD.top + plotH - (y / top) * plotH
  const allX = [...new Set(xs)].sort((a, b) => a - b)

  const onMove = (e: MouseEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const target = minX + ((e.clientX - box.left) / box.width) * (maxX - minX)
    const x = allX.reduce((best, v) => (Math.abs(v - target) < Math.abs(best - target) ? v : best), allX[0])
    setHoverX(x)
    setTip({
      x: sx(x),
      y: PAD.top,
      content: (
        <>
          <div className="muted">{formatX(x)}</div>
          {series.map((s) => {
            const point = s.points.find((p) => p[0] === x)
            return (
              <div key={s.key}>
                <span className="legend__key" style={{ background: s.color }} />
                <strong>{point ? point[1] : '—'}</strong> {s.label}
              </div>
            )
          })}
        </>
      ),
    })
  }

  const xTickCount = Math.max(2, Math.min(6, Math.floor(plotW / 110)))
  const xTicks = Array.from({ length: xTickCount }, (_, i) => minX + ((maxX - minX) * i) / (xTickCount - 1))

  return (
    <div className="chart" ref={ref}>
      {series.length > 1 && (
        <div className="legend">
          {series.map((s) => (
            <span key={s.key}>
              <span className="legend__key" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <svg width={width} height={height} role="img" aria-label="График жалоб в час">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={sy(t)} y2={sy(t)} stroke="var(--grid)" />
            <text x={PAD.left - 6} y={sy(t) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">
              {compact(t)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t} x={sx(t)} y={height - 6} textAnchor="middle" fontSize="11" fill="var(--muted)">
            {formatX(t)}
          </text>
        ))}
        {series.map((s) => (
          <path
            key={s.key}
            d={s.points.map((p, i) => `${i ? 'L' : 'M'}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join('')}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
        {hoverX !== null && (
          <>
            <line x1={sx(hoverX)} x2={sx(hoverX)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--axis)" />
            {series.map((s) => {
              const point = s.points.find((p) => p[0] === hoverX)
              return point ? (
                <circle key={s.key} cx={sx(point[0])} cy={sy(point[1])} r={4} fill={s.color}
                        stroke="var(--surface)" strokeWidth={2} />
              ) : null
            })}
          </>
        )}
        <rect x={PAD.left} y={PAD.top} width={plotW} height={plotH} fill="transparent"
              onMouseMove={onMove} onMouseLeave={() => { setTip(null); setHoverX(null) }} />
      </svg>
      <TipBox tip={tip} />
    </div>
  )
}
