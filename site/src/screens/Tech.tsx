import { useState } from 'react'
import { dayMonth, hm, SERVICE_SHORT, TITLES } from '../format'
import type { PrivateData, ServiceId } from '../types'

const PAGE = 100
const STATUS_TEXT: Record<string, string> = {
  OK: '✅ норма',
  OUTAGE: '🔴 сбой',
  SOURCE_ERROR: '❌ не ответил',
  DISABLED: '⚪ отключён',
}

function when(ts: string) {
  return `${dayMonth(ts)} ${hm(ts)}`
}

function SiteName({ svc, src, pages }: { svc: string; src: string; pages: Record<string, string> }) {
  const url = pages[`${svc}/${src}`]
  const title = TITLES[src] ?? src
  return url
    ? <a className="ext-link" href={url} target="_blank" rel="noreferrer" title={`Открыть страницу ${title}`}>{title} ↗</a>
    : <>{title}</>
}

// links in message texts become clickable
function Linkified({ text }: { text: string }) {
  return <>{text.split(/(https?:\/\/\S+?)(?=[.,;)]?(?:\s|$))/).map((part, i) => i % 2
    ? <a key={i} className="ext-link" href={part} target="_blank" rel="noreferrer">{part}</a>
    : part)}</>
}

export default function Tech({ priv, services, pages }: {
  priv: PrivateData
  services: ServiceId[]
  pages: Record<string, string>
}) {
  const [source, setSource] = useState('all')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(0)
  const rows = priv.checks.filter(([, svc, src, st]) => services.includes(svc)
    && (source === 'all' || src === source) && (status === 'all' || st === status))
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE))
  const shown = rows.slice(page * PAGE, page * PAGE + PAGE)
  const sources = [...new Set(priv.checks.map((r) => r[2]))]

  return (
    <>
      <section className="section card">
        <h2>Все проверки</h2>
        <p className="small muted">Все проверки за 2 суток и отклонения (сбой, нет ответа) за 30 дней, новые сверху.</p>
        <div className="pager" style={{ marginBottom: 10 }}>
          <select value={source} onChange={(e) => { setSource(e.target.value); setPage(0) }} aria-label="Сайт">
            <option value="all">все сайты</option>
            {sources.map((s) => <option key={s} value={s}>{TITLES[s] ?? s}</option>)}
          </select>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(0) }} aria-label="Статус">
            <option value="all">любой статус</option>
            {Object.entries(STATUS_TEXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span className="small dim">{rows.length} строк</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Время</th><th>Сервис</th><th>Сайт</th><th>Статус</th><th className="num">Жалоб/ч</th><th>Ответ сайта</th></tr>
            </thead>
            <tbody>
              {shown.map(([ts, svc, src, st, count, details], i) => (
                <tr key={ts + svc + src + i}>
                  <td className="num">{when(ts)}</td>
                  <td>{SERVICE_SHORT[svc]}</td>
                  <td><SiteName svc={svc} src={src} pages={pages} /></td>
                  <td>{STATUS_TEXT[st] ?? st}</td>
                  <td className="num">{count ?? ''}</td>
                  <td className="dim">{details}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {pageCount > 1 && (
          <div className="pager">
            <button className="link-button" disabled={page === 0} onClick={() => setPage(page - 1)}>← новее</button>
            <span className="small dim">стр. {page + 1} из {pageCount}</span>
            <button className="link-button" disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)}>старее →</button>
          </div>
        )}
      </section>

      <section className="section card">
        <h2>Когда сайты-мониторы не отвечали</h2>
        {priv.source_events.filter((e) => services.includes(e[2])).length ? (
          <table>
            <tbody>
              {priv.source_events.filter((e) => services.includes(e[2])).map(([ts, kind, svc, src, text]) => (
                <tr key={ts + kind + svc + src}>
                  <td className="num">{when(ts)}</td>
                  <td>{kind === 'source_down' ? '⚠️ перестал отвечать' : '✅ снова отвечает'}</td>
                  <td><SiteName svc={svc} src={src} pages={pages} /> · {SERVICE_SHORT[svc]}</td>
                  <td className="dim">{text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="small muted">Не было.</div>}
      </section>

      <section className="section card">
        <h2>Сообщения в чат</h2>
        {priv.messages.length ? priv.messages.slice(0, 200).map(([ts, text]) => (
          <div key={ts + text} style={{ borderTop: '1px solid var(--grid)', padding: '8px 0' }}>
            <div className="small muted">{when(ts)}</div>
            <pre className="pre"><Linkified text={text} /></pre>
          </div>
        )) : <div className="small muted">Пока не было (журнал сообщений ведётся с 15.10).</div>}
      </section>
    </>
  )
}
