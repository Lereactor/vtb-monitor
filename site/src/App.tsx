import { useCallback, useEffect, useState } from 'react'
import { decryptJson, importKey } from './crypto'
import { loadEncrypted, loadPublic } from './data'
import { ageMinutes, hm, PERIODS, SERVICE_FILTERS, services } from './format'
import Login, { KEY_STORAGE } from './Login'
import Analytics from './screens/Analytics'
import Incidents from './screens/Incidents'
import Now from './screens/Now'
import Tech from './screens/Tech'
import type { Period, PrivateData, PublicData, ServiceFilter } from './types'

type Tab = 'now' | 'incidents' | 'analytics' | 'tech'
const TABS: { id: Tab; label: string; private?: boolean }[] = [
  { id: 'now', label: 'Сейчас' },
  { id: 'incidents', label: 'Сбои' },
  { id: 'analytics', label: 'Аналитика' },
  { id: 'tech', label: 'Техника', private: true },
]
const REFRESH_MS = 60_000
const STALE_MINUTES = 15

/** Tab, filters and the open incident live in the URL hash, so a view can be shared as a link. */
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1))
  return {
    tab: (p.get('tab') as Tab) || 'now',
    service: (p.get('s') as ServiceFilter) || 'all',
    period: (p.get('p') as Period) || '7d',
    open: p.get('inc'),
  }
}

export default function App() {
  const [view, setView] = useState(readHash)
  const [data, setData] = useState<PublicData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [key, setKey] = useState<CryptoKey | null>(null)
  const [priv, setPriv] = useState<PrivateData | null>(null)
  const [login, setLogin] = useState(false)

  const update = (next: Partial<typeof view>) => {
    const merged = { ...view, ...next }
    setView(merged)
    const p = new URLSearchParams({ tab: merged.tab, s: merged.service, p: merged.period })
    if (merged.open) p.set('inc', merged.open)
    history.replaceState(null, '', `#${p}`)
  }

  const refresh = useCallback(async (withKey: CryptoKey | null) => {
    try {
      setData(await loadPublic())
      setError(null)
      if (withKey) setPriv(await decryptJson<PrivateData>(await loadEncrypted(), withKey))
    } catch {
      setError('Не удалось загрузить данные. Пробую снова через минуту.')
    }
  }, [])

  useEffect(() => {
    // a remembered key from «запомнить на этом устройстве»
    let saved: string | null = null
    try {
      saved = localStorage.getItem(KEY_STORAGE)
    } catch {
      saved = null
    }
    const start = saved
      ? importKey(saved).then((k) => { setKey(k); return k }).catch(() => null)
      : Promise.resolve(null)
    start.then((k) => refresh(k).catch(() => {
      // a stale key (password changed): forget it
      try { localStorage.removeItem(KEY_STORAGE) } catch { /* nothing to remove */ }
      setKey(null)
    }))
  }, [refresh])

  useEffect(() => {
    const timer = setInterval(() => refresh(key), REFRESH_MS)
    return () => clearInterval(timer)
  }, [key, refresh])

  const logout = () => {
    try { localStorage.removeItem(KEY_STORAGE) } catch { /* nothing to remove */ }
    setKey(null)
    setPriv(null)
    if (view.tab === 'tech') update({ tab: 'now' })
  }

  const age = data ? ageMinutes(data.generated_at) : 0
  const tab = view.tab === 'tech' && !priv ? 'now' : view.tab
  const filter = services(view.service)
  const pages = data ? Object.fromEntries(Object.entries(data.services).flatMap(([sid, s]) =>
    s.sources.filter((src) => src.url).map((src) => [`${sid}/${src.id}`, src.url as string]))) : {}

  return (
    <>
      <header className="top">
        <div className="top__row">
          <h1>Сбои ВТБ</h1>
          {data && (
            <span className={`top__updated${age > STALE_MINUTES ? ' top__updated--stale' : ''}`}>
              {age > STALE_MINUTES ? `⚠️ данные устарели: обновлено ${age} мин назад` : `обновлено в ${hm(data.generated_at)} МСК`}
            </span>
          )}
          <span className="top__spacer" />
          {priv
            ? <button className="link-button" onClick={logout} title="Забыть пароль на этом устройстве">Выйти</button>
            : <button className="link-button" onClick={() => setLogin(true)}>Войти</button>}
        </div>
        <div className="filters">
          <div className="seg" role="group" aria-label="Сервис">
            {SERVICE_FILTERS.map((s) => (
              <button key={s.id} aria-pressed={view.service === s.id} onClick={() => update({ service: s.id })}>{s.label}</button>
            ))}
          </div>
          {tab !== 'now' && tab !== 'tech' && (
            <div className="seg" role="group" aria-label="Период">
              {PERIODS.map((p) => (
                <button key={p.id} aria-pressed={view.period === p.id} onClick={() => update({ period: p.id })}>{p.label}</button>
              ))}
            </div>
          )}
        </div>
        <nav className="tabs" role="tablist">
          {TABS.filter((t) => !t.private || priv).map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => update({ tab: t.id })}>{t.label}</button>
          ))}
        </nav>
      </header>

      <main className="wrap">
        {error && <div className="error">{error}</div>}
        {!data && !error && <div className="empty">Загружаю…</div>}
        {data && tab === 'now' && <Now data={data} services={filter} />}
        {data && tab === 'incidents' && (
          <Incidents data={data} services={filter} period={view.period} priv={priv}
                     open={view.open} onOpen={(open) => update({ open })} pages={pages} />
        )}
        {data && tab === 'analytics' && (
          <Analytics block={data.analytics[`${view.period}|${view.service}`]} period={view.period} service={view.service}
                     pages={pages} />
        )}
        {priv && tab === 'tech' && <Tech priv={priv} services={filter} pages={pages} />}
      </main>

      {login && (
        <Login onClose={() => setLogin(false)} onDone={(k, p) => { setKey(k); setPriv(p); setLogin(false) }} />
      )}
    </>
  )
}
