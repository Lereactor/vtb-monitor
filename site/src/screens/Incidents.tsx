import Lines, { type Series } from '../charts/Lines'
import { dayMonth, duration, hm, inPeriod, SERVICE_SHORT, TITLES, weekdayDayTime } from '../format'
import type { Incident, Period, PrivateData, PublicData, ServiceId } from '../types'
import { seriesColor } from './colors'

function Detail({ incident, data, priv }: { incident: Incident; data: PublicData; priv: PrivateData | null }) {
  const start = new Date(incident.start).getTime()
  const end = incident.end ? new Date(incident.end).getTime() : Date.now()
  const from = start - 2 * 3600_000
  const to = end + 2 * 3600_000
  // hourly maxima of the last 30 days for this service
  const complaints = data.analytics[`30d|${incident.service}`]?.complaints ?? {}
  const series: Series[] = Object.entries(complaints).map(([key, points]) => ({
    key,
    label: TITLES[key.split('/')[1]],
    color: seriesColor(key),
    points: points
      .map(([hour, v]) => [new Date(`${hour}:00:00Z`).getTime(), v] as [number, number])
      .filter(([x]) => x >= from && x <= to),
  })).filter((s) => s.points.length)
  const messages = priv?.messages.filter(([ts]) => {
    const t = new Date(ts).getTime()
    return t >= start - 60_000 && t <= end + 60_000
  }) ?? []

  return (
    <div className="detail">
      <p>
        Порядок срабатывания: {incident.sources.map((s, i) => (
          <span className="chip" key={s}>{i + 1}. {TITLES[s] ?? s}</span>
        ))}
      </p>
      {incident.post && (
        <p>📢 Банк: «{incident.post.text.slice(0, 300)}» — <a href={incident.post.url} target="_blank" rel="noreferrer">пост</a>{' '}
          <span className="muted">в {hm(incident.post.ts)}</span></p>
      )}
      <h3 className="small dim">Жалобы в час вокруг сбоя (по часам)</h3>
      {series.length ? <Lines series={series} height={180} formatX={(x) => hm(new Date(x).toISOString())} />
        : <div className="small muted">Почасовых данных за это время нет (хранятся 30 дней).</div>}
      {priv && (
        <>
          <h3 className="small dim">Что ушло в чат</h3>
          {messages.length ? messages.map(([ts, text]) => (
            <div key={ts + text} className="card" style={{ marginBottom: 8 }}>
              <div className="small muted">{hm(ts)}</div>
              <pre className="pre">{text}</pre>
            </div>
          )) : <div className="small muted">Сообщений за это время нет.</div>}
        </>
      )}
    </div>
  )
}

export default function Incidents({ data, services, period, priv, open, onOpen }: {
  data: PublicData
  services: ServiceId[]
  period: Period
  priv: PrivateData | null
  open: string | null
  onOpen: (id: string | null) => void
}) {
  const list = data.incidents.filter((i) => services.includes(i.service)
    && (inPeriod(i.start, period) || (i.end !== null && inPeriod(i.end, period)) || i.end === null))
  if (!list.length) return <div className="empty section">За выбранный период сбоев не было.</div>

  return (
    <section className="section">
      <div className="small dim" style={{ marginBottom: 8 }}>
        Сбоев: {list.length}. Нажмите на строку, чтобы открыть подробности.
      </div>
      <div className="card list">
        {list.map((incident) => {
          const id = `${incident.service}-${incident.start}`
          const isOpen = open === id
          return (
            <div key={id}>
              <button className="incident" onClick={() => onOpen(isOpen ? null : id)} aria-expanded={isOpen}>
                <span className="incident__when">{weekdayDayTime(incident.start)}</span>
                <span>
                  <strong>{SERVICE_SHORT[incident.service]}</strong>
                  {incident.end === null ? <span className="tag">идёт</span> : null}
                  {incident.solo && <span className="tag">возможно, ложная тревога</span>}
                  {incident.post && <span className="tag">📢 банк подтвердил</span>}
                </span>
                <span className="dim">{incident.end === null ? `${duration(incident.minutes)} и идёт` : duration(incident.minutes)}</span>
                <span className="incident__meta">
                  {incident.sources.map((s) => TITLES[s] ?? s).join(' → ')}
                  {incident.peak ? ` · пик ${incident.peak} жалоб в час` : null}
                  {incident.end && ` · до ${dayMonth(incident.end) === dayMonth(incident.start) ? '' : dayMonth(incident.end) + ' '}${hm(incident.end)}`}
                </span>
              </button>
              {isOpen && <Detail incident={incident} data={data} priv={priv} />}
            </div>
          )
        })}
      </div>
    </section>
  )
}
