import { describe, expect, it } from 'vitest'
import { ageMinutes, duration, hm, inPeriod } from './format'

describe('format', () => {
  it('shows Moscow time', () => {
    expect(hm('2026-10-15T09:05:00+00:00')).toBe('12:05')
  })

  it('formats durations like the summary text', () => {
    expect(duration(35)).toBe('35 мин')
    expect(duration(65)).toBe('1 ч 05 мин')
    expect(duration(120)).toBe('2 ч')
  })

  it('checks periods', () => {
    const now = Date.parse('2026-10-15T09:00:00Z')
    expect(inPeriod('2026-10-14T10:00:00+00:00', '24h', now)).toBe(true)
    expect(inPeriod('2026-10-14T08:00:00+00:00', '24h', now)).toBe(false)
    expect(inPeriod('2020-01-01T00:00:00+00:00', 'all', now)).toBe(true)
    expect(ageMinutes('2026-10-15T08:45:00+00:00', now)).toBe(15)
  })
})
