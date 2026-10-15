import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Charts draw at the real pixel width, so 2px lines and text stay crisp. */
export function useWidth<T extends HTMLElement>(initial = 600) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(initial)
  useEffect(() => {
    if (!ref.current) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, Math.floor(entry.contentRect.width))))
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])
  return { ref, width }
}

export interface Tip {
  x: number
  y: number
  content: ReactNode
}

/** One tooltip per chart, positioned inside the chart's relative wrapper. */
export function TipBox({ tip }: { tip: Tip | null }) {
  if (!tip) return null
  return (
    <div className="tip" style={{ left: tip.x, top: tip.y }}>
      {tip.content}
    </div>
  )
}

/** Clean axis ticks: 0, then round steps up to the max. */
export function ticks(max: number, count = 4): number[] {
  if (max <= 0) return [0]
  const raw = max / count
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw
  const out = []
  for (let v = 0; v <= max + step / 2; v += step) out.push(Math.round(v * 100) / 100)
  return out
}

export function compact(n: number): string {
  return n >= 1000 ? `${Math.round(n / 100) / 10}K` : String(n)
}
