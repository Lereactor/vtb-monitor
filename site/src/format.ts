import type { Period, ServiceFilter, ServiceId, Status } from './types'

const MSK = 'Europe/Moscow'

export const SERVICE_SHORT: Record<ServiceId, string> = { vtb: 'ВТБ', invest: 'Мои Инвестиции' }
export const SERVICE_FILTERS: { id: ServiceFilter; label: string }[] = [
  { id: 'all', label: 'Все' },
  { id: 'vtb', label: 'ВТБ' },
  { id: 'invest', label: 'Мои Инвестиции' },
]
export const PERIODS: { id: Period; label: string; hours: number | null }[] = [
  { id: '24h', label: '24 ч', hours: 24 },
  { id: '7d', label: '7 д', hours: 24 * 7 },
  { id: '30d', label: '30 д', hours: 24 * 30 },
  { id: 'all', label: 'Всё', hours: null },
]
export const TITLES: Record<string, string> = {
  detector404: 'DETECTOR404',
  downreport: 'DownReport',
  downradar: 'DownRadar',
  sboyrf: 'СБОЙ.РФ',
  telegram: 'Telegram ВТБ',
}

export const STATUS: Record<Status, { icon: string; label: string }> = {
  ok: { icon: '✅', label: 'норма' },
  outage: { icon: '🔴', label: 'видит сбой' },
  broken: { icon: '❌', label: 'не отвечает' },
  disabled: { icon: '⚪', label: 'отключён' },
  unknown: { icon: '❔', label: 'нет данных' },
}

export function hm(ts: string): string {
  return new Date(ts).toLocaleTimeString('ru-RU', { timeZone: MSK, hour: '2-digit', minute: '2-digit' })
}

export function dayMonth(ts: string): string {
  return new Date(ts).toLocaleDateString('ru-RU', { timeZone: MSK, day: '2-digit', month: '2-digit' })
}

export function weekdayDayTime(ts: string): string {
  const d = new Date(ts)
  const wd = d.toLocaleDateString('ru-RU', { timeZone: MSK, weekday: 'short' })
  return `${wd} ${dayMonth(ts)} ${hm(ts)}`
}

export function duration(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (!h) return `${m} мин`
  return m ? `${h} ч ${String(m).padStart(2, '0')} мин` : `${h} ч`
}

export function percent(share: number): string {
  return `${(share * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`
}

export function ageMinutes(ts: string, now = Date.now()): number {
  return Math.floor((now - new Date(ts).getTime()) / 60000)
}

export function inPeriod(ts: string, period: Period, now = Date.now()): boolean {
  const hours = PERIODS.find((p) => p.id === period)!.hours
  return hours === null || new Date(ts).getTime() >= now - hours * 3600_000
}

export function services(filter: ServiceFilter): ServiceId[] {
  return filter === 'all' ? ['vtb', 'invest'] : [filter]
}
