/** Color follows the entity, never its rank: each complaints series keeps its slot under any filter.
 *  Three slots only — the first three of the validated palette pass all-pairs in both themes. */
const SLOTS: Record<string, string> = {
  'business/downradar': 'var(--s1)',
  'invest/downradar': 'var(--s2)',
}

export function seriesColor(key: string): string {
  return SLOTS[key] ?? 'var(--muted)'
}
