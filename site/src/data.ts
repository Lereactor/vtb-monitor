import type { Encrypted, PublicData } from './types'

/** The VPS force-pushes the data branch every 5 minutes; raw.githubusercontent caches up to 5 min.
 *  In dev, sample files from scripts/make_sample_data.py are served from /sample/. */
const BASE = import.meta.env.DEV
  ? '/sample/'
  : 'https://raw.githubusercontent.com/Lereactor/vtb-monitor-live/data/'

function url(name: string): string {
  return `${BASE}${name}?t=${Math.floor(Date.now() / 60000)}` // at most one fresh fetch a minute
}

export async function loadPublic(): Promise<PublicData> {
  const res = await fetch(url('public.json'), { cache: 'no-store' })
  if (!res.ok) throw new Error(`public.json: HTTP ${res.status}`)
  return (await res.json()) as PublicData
}

export async function loadEncrypted(): Promise<Encrypted> {
  const res = await fetch(url('private.enc'), { cache: 'no-store' })
  if (!res.ok) throw new Error(`private.enc: HTTP ${res.status}`)
  return (await res.json()) as Encrypted
}
