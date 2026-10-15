import { useState } from 'react'
import { TipBox, type Tip } from './common'

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

/** Weekday × hour (MSK): one hue, more complaints = more opaque, so low values recede to the surface. */
export default function Heatmap({ cells }: { cells: (number | null)[][] }) {
  const [tip, setTip] = useState<Tip | null>(null)
  const values = cells.flat().filter((v): v is number => v !== null)
  if (!values.length) return <div className="empty">Нет данных за период</div>
  const max = Math.max(1, ...values)

  return (
    <div className="chart" onMouseLeave={() => setTip(null)}>
      <div className="heat" role="img" aria-label="Жалобы по дням недели и часам">
        <span />
        {Array.from({ length: 24 }, (_, h) => (
          <span key={h} style={{ textAlign: 'center' }}>{h % 3 === 0 ? h : ''}</span>
        ))}
        {cells.map((row, d) => [
          <span key={`l${d}`} className="heat__label">{DAYS[d]}</span>,
          ...row.map((v, h) => (
            <div
              key={`${d}-${h}`}
              className="heat__cell"
              style={{
                background: v === null ? 'var(--surface-2)' : 'var(--s1)',
                opacity: v === null ? 1 : 0.08 + 0.92 * (v / max),
              }}
              onMouseEnter={(e) => {
                const cell = e.currentTarget.getBoundingClientRect()
                const box = e.currentTarget.parentElement!.getBoundingClientRect()
                setTip({
                  x: cell.left - box.left + cell.width / 2,
                  y: cell.top - box.top,
                  content: (
                    <>
                      <span className="muted">{DAYS[d]}, {String(h).padStart(2, '0')}:00</span>{' '}
                      <strong>{v === null ? 'нет данных' : `${v} жалоб в час`}</strong>
                    </>
                  ),
                })
              }}
            />
          )),
        ])}
      </div>
      <div className="small muted" style={{ marginTop: 6 }}>
        Светлее — меньше жалоб, темнее — больше (до {Math.round(max)} в час). Время московское.
      </div>
      <TipBox tip={tip} />
    </div>
  )
}
