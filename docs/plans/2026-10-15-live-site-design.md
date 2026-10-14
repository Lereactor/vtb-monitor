# Live site and analytics — design

Date: 2026-10-15
Scope: a web site to watch the detectors live, filter incidents by service, and read
analytics (BI) with a plain-language summary. Built the same way as the «Мои агенты»
site in `C:\Claude\Agents` (static React site on GitHub Pages, password gate).

## Audiences: two levels

| Level | Who | What |
|---|---|---|
| Open, no password | anyone with the link | current status, incident feed, analytics, summary |
| Password | the owner and the team | technical details: every check, monitor errors, sent messages |

The password is the same as on the agents site. It never reaches the VPS or git (see Secrets).

## Data flow

```
VPS, every 5 min (vtb-monitor.service)
  checks → alerts (unchanged)
         → history.db (SQLite)            ← posts.json from GitHub (official channel)
         → build public.json + private.enc
         → git push -f to Lereactor/vtb-monitor-live (GitHub Pages)
browser → reads public.json; after login decrypts private.enc
```

A failed history write or upload must never block alerts: it is logged and retried on
the next run. The site shows the time of the last update and warns when it is older
than 15 minutes.

## 1. History (VPS)

`/var/lib/vtb-monitor/history.db`, written by `monitor/history.py`:

- `checks`: ts, service, source, status, count (complaints per hour, if the site gives
  one), details. One row per source per run, about 2000 rows a day.
- `events`: ts, service, kind (`incident_started`, `incident_confirmed`,
  `incident_resolved`, `source_down`, `source_back`, `message_sent`), source, text.
- `posts`: official @bankvtb posts (id, ts, kind, text, url).

`SourceResult` gains an optional `count` field: DownRadar and СБОЙ.РФ give complaints per
hour; DETECTOR404 and DownReport give no number (count stays empty).

Retention: rows in `checks` older than 90 days are rolled up into hourly totals;
events and posts are kept forever. Expected size: well under 100 MB a year.

Backfill: the systemd journal on the VPS holds check lines since 2026-10-09
(`[service/source] STATUS details`). A one-off script parses them into `checks`;
incidents are rebuilt by replaying the same state machine over the backfilled checks.

## 2. Official channel posts

The channel is read on GitHub (Telegram is blocked on the VPS). The `vtb-monitor`
workflow appends new matching posts to `posts.json` in the repo (public data anyway)
and commits it with `state.json`. The VPS reads that file through the GitHub API on
each run and upserts into `posts`.

## 3. Export (VPS → site)

`monitor/export.py` builds, after every run:

- `public.json`: generated time; per service the current status and each site's status,
  last count and 24 h sparkline; the incident list (start, end, duration, sites in the
  order they joined, peak count, matching bank post); pre-aggregated analytics per
  period (24 h, 7 d, 30 d, all) and per service filter (all, ВТБ, Инвестиции); the summary text.
- `private.enc`: every check row (90 days), monitor error timeline, sent messages,
  encrypted with AES-GCM under a key derived from the site password
  (PBKDF2-SHA256, 600 000 iterations, the agents-site scheme).

Analytics are computed on the VPS so the browser only draws.

### Analytics

- Incidents: count and total duration per day/week, ВТБ vs Инвестиции, share of time
  without an incident.
- Complaints over time: complaints per hour per site; heatmap weekday × hour.
- Monitor quality: who detects first, share of solo alarms (only that site saw it —
  likely false), how long the site itself was not answering.
- Bank confirmations: share of incidents with a matching bank post (post within
  the incident or 60 min after its start), median lead of the notifier over the post.
- Summary: rule-based text from the same numbers, e.g. «За неделю: 2 сбоя ВТБ,
  суммарно 35 мин; самый длинный — вт 15:25 (20 мин). Банк подтвердил 1 из 2.
  Первым срабатывал DETECTOR404. DownRadar не отвечал 3 раза.» No LLM.

## 4. Site

Static React + Vite + TypeScript, like `ai-agent-live/frontend`. A small chart
library, no BI engine. Light and dark theme; one column on phones, no horizontal scroll.

Header on every screen: service filter (все / ВТБ / Мои Инвестиции), period
(24 ч / 7 д / 30 д / всё), last update time, «Войти» / «Выйти».

1. **Сейчас** — one block per service («✅ ВТБ: всё в норме» or «🔴 похоже на сбой с 15:25,
   видят 2 сайта из 4»), then a card per site: ✅/🔴/❌, last count, 24 h sparkline, last
   check time. Reloads `public.json` every minute.
2. **Сбои** — incident feed: service, start, duration, sites in order, peak, 📢 bank post,
   «возможно, ложная тревога» for solo incidents. Click → incident timeline with all
   sites' complaints around it and the messages sent.
3. **Аналитика** — summary text, KPI tiles, charts and tables listed above.
4. **Техника** (password) — checks table filtered by site and status, monitor error
   timeline, sent messages log.

## Secrets

- Site password: entered once on the owner's PC to derive the key; only the derived
  key and salt go to `/etc/vtb-monitor.env` (root-only). The key cannot open the
  agents site. The browser derives the same key from the typed password.
- Push access: an SSH deploy key with write access to `Lereactor/vtb-monitor-live` only.
  The existing GitHub token (Telegram relay) is unchanged.

## Disk

The VPS root has about 470 MB free (90% used). The morning report gains a warning when
free space drops below 200 MB.

## Testing

- Unit tests: history writes and roll-up, journal backfill on real VPS log lines,
  incident analytics (durations, first detector, solo alarms, bank lead), summary text,
  encryption round trip compatible with the browser (WebCrypto) scheme.
- A check that `public.json` holds nothing from the private set.
- Site checked in a browser on real data, including phone width.

## Rollout (each step works on its own)

1. History in SQLite + backfill from 2026-10-09. Alerts unchanged.
2. Channel workflow writes `posts.json`; VPS imports it.
3. Export of `public.json` / `private.enc` with analytics and summary.
4. Site: four screens, filters, login.
5. Repo `vtb-monitor-live`, GitHub Pages, deploy key, upload after every run.

## Known limits

- History starts on 2026-10-09.
- With a handful of incidents the analytics say little; the heatmap and «who is first»
  get useful after a few weeks.
