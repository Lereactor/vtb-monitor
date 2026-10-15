/** Mirrors monitor/export.py: public.json and the decrypted private part. */

export type Status = 'ok' | 'outage' | 'broken' | 'disabled' | 'unknown'
export type ServiceId = 'vtb' | 'invest'
export type ServiceFilter = 'all' | ServiceId
export type Period = '24h' | '7d' | '30d' | 'all'

export interface SourceNow {
  status: Status
  checked_at: string | null
  count: number | null
  details: string
  spark: [string, number | null, string][] // ts, complaints/hour, raw check status
}

export interface ServiceNow {
  incident: { start: string; sources: string[] } | null
  working: number
  total: number
  sources: Record<string, SourceNow>
}

export interface Post {
  id: number
  ts: string
  text: string
  url: string
}

export interface Incident {
  service: ServiceId
  start: string
  end: string | null
  minutes: number
  sources: string[]
  peak: number | null
  solo: boolean
  post: Post | null
}

export interface MonitorRow {
  service: ServiceId
  source: string
  title: string
  first: number
  solo: number
  alarms: number
  down_episodes: number
  error_minutes: number
}

export interface Block {
  kpi: { incidents: number; minutes: number; uptime: number; confirmed: number; lead_min: number | null }
  per_day: { date: string; incidents: number; minutes: number }[]
  complaints: Record<string, [string, number][]> // "service/source" → [hour or day, max complaints]
  heatmap: (number | null)[][] // 7 MSK weekdays × 24 hours
  monitors: MonitorRow[]
  summary: string
}

export interface PublicData {
  generated_at: string
  services: Record<ServiceId, { title: string; sources: { id: string; title: string }[] }>
  now: Record<ServiceId, ServiceNow>
  incidents: Incident[]
  analytics: Record<string, Block> // "<period>|<service filter>"
}

export interface PrivateData {
  checks: [string, ServiceId, string, string, number | null, string][] // ts, service, source, status, count, details
  source_events: [string, string, ServiceId, string, string][] // ts, kind, service, source, text
  messages: [string, string][] // ts, text
}

export interface Encrypted {
  v: 1
  iter: number
  salt: string
  iv: string
  ct: string
}
