import ReachStrip from '../charts/ReachStrip'
import Sparkline from '../charts/Sparkline'
import { hm, reachIcon, REGION_TITLES, SERVICE_SHORT, STATUS, TITLES } from '../format'
import type { PublicData, Region, ServiceId, SiteNow } from '../types'

function Banner({ data, service }: { data: PublicData; service: ServiceId }) {
  const now = data.now[service]
  const title = data.services[service].title
  if (!now.incident) {
    return (
      <div className="banner">
        <strong>✅ {title}: всё в норме</strong>
        <span className="dim">отвечают сайтов: {now.working} из {now.total}</span>
      </div>
    )
  }
  const seeing = now.incident.sources.length
  // the incident closes only after RECOVERY_RUNS calm checks in a row (monitor/state.py)
  const calm = Object.values(now.sources).every((s) => s.status !== 'outage')
  return (
    <div className="banner banner--outage">
      <strong>🔴 {title}: похоже на сбой с {hm(now.incident.start)}</strong>
      <span className="dim">
        {calm
          ? 'сайты уже в норме — сбой закроется после двух спокойных проверок подряд'
          : <>видят сайтов: {seeing} из {now.working}{seeing === 1 && ' — пока один, возможна ложная тревога'}</>}
      </span>
    </div>
  )
}

function Site({ site }: { site: SiteNow }) {
  return (
    <div className="card">
      <div className="source__head">
        <a className="source__name ext-link" href={site.url} target="_blank" rel="noreferrer"
           title={`Открыть ${site.host}`}>{site.host} ↗</a>
      </div>
      {(['ru', 'world'] as Region[]).map((region) => {
        const r = site[region]
        return (
          <div className="reach" key={region}>
            <div className="reach__head">
              <span className="small dim">{REGION_TITLES[region]}</span>
              <span className="pill" title={r?.details}>
                {r ? <>{reachIcon(r.up, r.total)} {r.up} из {r.total}{r.ms !== null && ` · ${r.ms} мс`}</> : '❔ нет данных'}
              </span>
            </div>
            {r && <ReachStrip points={r.spark} label={REGION_TITLES[region]} />}
          </div>
        )
      })}
      <div className="small muted">
        {site.ru ? `проверено в ${hm(site.ru.checked_at)}` : 'ещё не проверялся'} · сутки
      </div>
    </div>
  )
}

export default function Now({ data, services }: { data: PublicData; services: ServiceId[] }) {
  return (
    <>
      {services.map((service) => (
        <section className="section" key={service}>
          <Banner data={data} service={service} />
          <div className="grid">
            {data.services[service].sources.map(({ id, url }) => {
              const source = data.now[service].sources[id]
              const status = STATUS[source.status]
              return (
                <div className="card" key={id}>
                  <div className="source__head">
                    {url
                      ? <a className="source__name ext-link" href={url} target="_blank" rel="noreferrer"
                           title={`Открыть страницу ${TITLES[id] ?? id}`}>{TITLES[id] ?? id} ↗</a>
                      : <span className="source__name">{TITLES[id] ?? id}</span>}
                    <span className="pill">{status.icon} {status.label}</span>
                  </div>
                  <div className="source__count">
                    {source.count !== null ? (
                      <>{source.count} <span className="small dim">жалоб за час</span></>
                    ) : (
                      <span className="small dim">{source.details || '—'}</span>
                    )}
                  </div>
                  <Sparkline points={source.spark} />
                  <div className="small muted">
                    {source.checked_at ? `проверено в ${hm(source.checked_at)}` : 'ещё не проверялся'} · сутки
                  </div>
                </div>
              )
            })}
          </div>
          {(data.now[service].sites ?? []).length > 0 && (
            <>
              <h3 className="subhead">Открываются ли сайты {SERVICE_SHORT[service]}</h3>
              <div className="grid">
                {data.now[service].sites.map((site) => <Site key={site.host} site={site} />)}
              </div>
            </>
          )}
        </section>
      ))}
      <p className="small muted section">
        Проверки каждые 5 минут. {SERVICE_SHORT.business} — интернет-банк для бизнеса (db.vtb.ru,
        старый vtbbo.ru), {SERVICE_SHORT.invest} — брокерское приложение. Жалобы пользователей — ранний
        сигнал, подтверждённый сбой — только сообщение банка. Открываются ли сайты, проверяется из России
        (сервер оповещателя и точки check-host.net в Москве и Петербурге) и из-за рубежа (Франкфурт,
        Амстердам, Лондон, Лос-Анджелес): это дополнительный показатель, тревогу он не поднимает.
      </p>
    </>
  )
}
