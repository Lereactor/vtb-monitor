import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { PrivateData } from '../types'
import Tech from './Tech'

const priv: PrivateData = {
  checks: [['2026-10-15T10:00:00+03:00', 'invest', 'downradar', 'OK', 3, '']],
  source_events: [['2026-10-15T09:00:00+03:00', 'source_down', 'vtb', 'detector404', 'таймаут']],
  messages: [['2026-10-15T09:00:00+03:00', 'ВТБ\nПодробнее: https://downreport.ru/vtb']],
}
const pages = {
  'invest/downradar': 'https://downradar.ru/ne-rabotaet/broker.vtb.ru',
  'vtb/detector404': 'https://detector404.ru/bank-vtb',
}

describe('Tech', () => {
  it('links monitor names and urls in messages', () => {
    const html = renderToStaticMarkup(<Tech priv={priv} services={['vtb', 'invest']} pages={pages} />)
    expect(html).toContain('href="https://downradar.ru/ne-rabotaet/broker.vtb.ru"')
    expect(html).toContain('href="https://detector404.ru/bank-vtb"')
    expect(html).toContain('<a class="ext-link" href="https://downreport.ru/vtb"')
    expect(html).toContain('ВТБ\nПодробнее: ')
  })
})
