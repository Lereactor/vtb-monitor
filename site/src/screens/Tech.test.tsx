import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { PrivateData } from '../types'
import Tech from './Tech'

const priv: PrivateData = {
  checks: [['2026-10-15T10:00:00+03:00', 'invest', 'downradar', 'OK', 3, '']],
  source_events: [['2026-10-15T09:00:00+03:00', 'source_down', 'business', 'downradar', 'таймаут']],
  messages: [['2026-10-15T09:00:00+03:00', 'ВТБ\nПодробнее: https://downreport.ru/vtb']],
  reach: [['2026-10-15T09:00:00+03:00', 'business', 'db.vtb.ru', 'ru', 3, 4, 'Москва ❌ таймаут']],
}
const pages = {
  'invest/downradar': 'https://downradar.ru/ne-rabotaet/broker.vtb.ru',
  'business/downradar': 'https://downradar.ru/ne-rabotaet/db.vtb.ru',
}

describe('Tech', () => {
  it('links monitor names and urls in messages', () => {
    const html = renderToStaticMarkup(<Tech priv={priv} services={['business', 'invest']} pages={pages} />)
    expect(html).toContain('href="https://downradar.ru/ne-rabotaet/broker.vtb.ru"')
    expect(html).toContain('href="https://downradar.ru/ne-rabotaet/db.vtb.ru"')
    expect(html).toContain('<a class="ext-link" href="https://downreport.ru/vtb"')
    expect(html).toContain('ВТБ\nПодробнее: ')
  })

  it('lists bank sites that did not open from everywhere', () => {
    const html = renderToStaticMarkup(<Tech priv={priv} services={['business']} pages={pages} />)
    expect(html).toContain('href="https://db.vtb.ru/"')
    expect(html).toContain('⚠️ 3 из 4')
    expect(html).toContain('Москва ❌ таймаут')
    expect(renderToStaticMarkup(<Tech priv={priv} services={['invest']} pages={pages} />)).not.toContain('Москва ❌')
  })
})
