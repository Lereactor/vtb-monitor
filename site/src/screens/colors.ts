/** Color follows the entity, never its rank: each complaints series keeps its slot under any filter.
 *  Three slots only — the first three of the validated palette pass all-pairs in both themes. */
const SLOTS: Record<string, string> = {
  'vtb/sboyrf': 'var(--s1)',
  'vtb/downradar': 'var(--s2)',
  'invest/downradar': 'var(--s3)',
}

export function seriesColor(key: string): string {
  return SLOTS[key] ?? 'var(--muted)'
}
