import Sparkline from '../charts/Sparkline'
import { hm, SERVICE_SHORT, STATUS, TITLES } from '../format'
import type { PublicData, ServiceId } from '../types'

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

export default function Now({ data, services }: { data: PublicData; services: ServiceId[] }) {
  return (
    <>
      {services.map((service) => (
        <section className="section" key={service}>
          <Banner data={data} service={service} />
          <div className="grid">
            {data.services[service].sources.map(({ id }) => {
              const source = data.now[service].sources[id]
              const status = STATUS[source.status]
              return (
                <div className="card" key={id}>
                  <div className="source__head">
                    <span className="source__name">{TITLES[id] ?? id}</span>
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
        </section>
      ))}
      <p className="small muted section">
        Сайты проверяются каждые 5 минут. {SERVICE_SHORT.vtb} — банк и ВТБ Онлайн,{' '}
        {SERVICE_SHORT.invest} — брокерское приложение. Жалобы пользователей — ранний сигнал,
        подтверждённый сбой — только сообщение банка.
      </p>
    </>
  )
}
