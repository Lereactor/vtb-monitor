import Bars from '../charts/Bars'
import Heatmap from '../charts/Heatmap'
import Lines, { type Series } from '../charts/Lines'
import { dayMonth, duration, hm, percent, SERVICE_SHORT, TITLES } from '../format'
import type { Block, Period, ServiceFilter, ServiceId } from '../types'
import { seriesColor } from './colors'

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="card">
      <div className="tile__label">{label}</div>
      <div className="tile__value">{value}</div>
      {note && <div className="tile__note">{note}</div>}
    </div>
  )
}

export default function Analytics({ block, period, service, pages }: {
  block: Block
  period: Period
  /** "service/source" -> the monitor's page */
  pages: Record<string, string>
  service: ServiceFilter
}) {
  const { kpi } = block
  const daily = period === 'all'
  const complaints: Series[] = Object.entries(block.complaints)
    .filter(([, points]) => points.some(([, v]) => v > 0))
    .map(([key, points]) => {
      const [svc, source] = key.split('/')
      return {
        key,
        label: service === 'all' ? `${TITLES[source]} · ${SERVICE_SHORT[svc as ServiceId]}` : TITLES[source],
        color: seriesColor(key),
        points: points.map(([t, v]) => [new Date(daily ? `${t}T00:00:00Z` : `${t}:00:00Z`).getTime(), v] as [number, number]),
      }
    })
  const formatX = period === '24h'
    ? (x: number) => hm(new Date(x).toISOString())
    : (x: number) => dayMonth(new Date(x).toISOString())

  return (
    <>
      <section className="section">
        <div className="card summary">{block.summary}</div>
      </section>

      <section className="section tiles">
        <Tile label="Сбоев" value={String(kpi.incidents)} note={kpi.incidents ? `суммарно ${duration(kpi.minutes)}` : undefined} />
        <Tile label="Время без сбоев" value={percent(kpi.uptime)} />
        <Tile label="Подтвердил банк" value={kpi.incidents ? `${kpi.confirmed} из ${kpi.incidents}` : '—'}
              note={kpi.lead_min !== null ? `пост в среднем через ${kpi.lead_min} мин после начала` : undefined} />
        <Tile label="Одиночных срабатываний" value={String(block.monitors.reduce((n, m) => n + m.solo, 0))}
              note="сбой видел только один сайт — возможно, ложная тревога" />
      </section>

      <section className="section card">
        <h2>Сбои по дням</h2>
        <Bars bars={block.per_day.map((d) => ({
          label: dayMonth(`${d.date}T12:00:00+03:00`),
          value: d.incidents,
          tip: <><span className="muted">{dayMonth(`${d.date}T12:00:00+03:00`)}</span> <strong>{d.incidents}</strong> сбоев{d.minutes ? `, ${duration(d.minutes)}` : ''}</>,
        }))} />
      </section>

      <section className="section card">
        <h2>Жалобы в час {daily && <span className="small dim">(максимум за день)</span>}</h2>
        {complaints.length ? <Lines series={complaints} formatX={formatX} />
          : <div className="empty">DownRadar (единственный сайт с числом жалоб) за период ничего не показал.</div>}
      </section>

      <section className="section card">
        <h2>Когда больше всего жалоб</h2>
        <Heatmap cells={block.heatmap} />
      </section>

      {(block.sites ?? []).length > 0 && (
        <section className="section card">
          <h2>Открываются ли сайты банка</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Сайт</th>
                  {service === 'all' && <th>Сервис</th>}
                  <th className="num">Из России</th>
                  <th className="num">Из-за рубежа</th>
                  <th className="num">Не открывался из России, мин</th>
                  <th className="num">Из-за рубежа, мин</th>
                </tr>
              </thead>
              <tbody>
                {block.sites.map((s) => (
                  <tr key={s.service + s.host}>
                    <td><a className="ext-link" href={`https://${s.host}/`} target="_blank" rel="noreferrer"
                           title={`Открыть ${s.host}`}>{s.host} ↗</a></td>
                    {service === 'all' && <td>{SERVICE_SHORT[s.service]}</td>}
                    <td className="num">{s.ru.share !== null ? percent(s.ru.share) : '—'}</td>
                    <td className="num">{s.world.share !== null ? percent(s.world.share) : '—'}</td>
                    <td className="num">{s.ru.dark_minutes}</td>
                    <td className="num">{s.world.dark_minutes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted">
            Процент — доля точек проверки, где сайт ответил. «Не открывался» — сколько минут сайт не ответил
            ни в одной точке региона (хотя бы двух). Это дополнительный показатель: тревогу он не поднимает.
          </p>
        </section>
      )}

      <section className="section card">
        <h2>Сайты-мониторы</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Сайт</th>
                {service === 'all' && <th>Сервис</th>}
                <th className="num">Срабатываний</th>
                <th className="num">Первым</th>
                <th className="num">Одиночных</th>
                <th className="num">Не отвечал, раз</th>
                <th className="num">Без ответа, мин</th>
              </tr>
            </thead>
            <tbody>
              {block.monitors.map((m) => (
                <tr key={m.service + m.source}>
                  <td>
                    {pages[`${m.service}/${m.source}`]
                      ? <a className="ext-link" href={pages[`${m.service}/${m.source}`]} target="_blank" rel="noreferrer"
                           title={`Открыть страницу ${m.title}`}>{m.title} ↗</a>
                      : m.title}
                  </td>
                  {service === 'all' && <td>{SERVICE_SHORT[m.service]}</td>}
                  <td className="num">{m.alarms}</td>
                  <td className="num">{m.first}</td>
                  <td className="num">{m.solo}</td>
                  <td className="num">{m.down_episodes}</td>
                  <td className="num">{m.error_minutes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted">
          «Одиночных» — сбой видел только этот сайт: чем их больше, тем чаще сайт даёт ложные тревоги.
          «Без ответа» — сколько минут сам сайт не отвечал на проверки.
        </p>
      </section>
    </>
  )
}
