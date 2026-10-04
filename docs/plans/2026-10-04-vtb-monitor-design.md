# VTB outage notifier — design

Date: 2026-10-04
Scope: narrow MVP of `bank_outage_monitoring_agent_spec.md` — one bank (ВТБ), alerts to Telegram.

## Goal

Send a Telegram message when public outage detectors or the official VTB channel
report a VTB outage, naming the source(s). Report recovery and broken sources too.

## Runtime

- GitHub Actions, public repo, cron `*/5 * * * *` (real delay 5–15 min).
- One Python script per run, ~20 s. Deps: `requests`, `beautifulsoup4`.
- `concurrency: vtb-monitor` — no overlapping runs.
- State in `state.json`, committed back by the workflow only when changed.
- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DETECTOR404_TOKEN` (optional).

## Sources

Each source returns `OK`, `OUTAGE` (with details) or `SOURCE_ERROR`.
A missing token gives `DISABLED`, which is not an error.

| Source | How | OUTAGE when |
|---|---|---|
| DETECTOR404 | API `GET /api/v1/alerts` (active events), Bearer token | An active event mentions VTB (item format to finalise once a token exists) |
| DownReport | HTML `https://downreport.ru/vtb` | Status class `text-danger` (`text-warning` «Жалобы на сбои» = isolated reports → OK) |
| DownRadar | HTML `https://downradar.ru/ne-rabotaet/vtb.ru` | «Статус Vtb.ru : есть проблемы» (detector compares to its own baseline) |
| Telegram @bankvtb | HTML `https://t.me/s/bankvtb` | Never an incident source: matching posts are forwarded as 📢 official messages; status is only source health |

Excluded:
- Downdetector: Cloudflare challenge, ToS forbids scraping; only the paid Enterprise API is legitimate.
- DownScope: no public VTB page.
- vtb.ru synthetic check: Russian root CA plus foreign GitHub IPs make it meaningless.
- CBR RSS: no outage info.

Parsers that cannot find the expected marker return `SOURCE_ERROR`, never `OK`.

## Alert rules (state transitions only)

- Crowd sources (DownReport, DownRadar) need `OUTAGE` on 2 consecutive runs.
  DETECTOR404 counts immediately. A SOURCE_ERROR resets the 2-run streak.
- While an incident is open, a detector whose latest non-error result is `OUTAGE`
  counts as in outage even if its streak was reset, so a flapping source
  (O,O,K,O,O,K…) gives one 🔴, not 🔴 🟢 🔴 🟢.
- A detector that is DISABLED, or has failed 3 runs in a row (⚙️ sent), stops
  counting as in outage, so a stale `OUTAGE` cannot hold an incident open forever.
- 🔴 First source enters OUTAGE: «ВТБ: возможный сбой», source, numbers, link, all-source summary.
- ➕ Another source joins during an incident: «сбой подтверждает X (N из M)»; N = detectors
  in outage now, M = detectors not DISABLED.
- 🟢 No detector in outage for 2 consecutive runs: «сбой завершён, длительность». If any
  detector is erroring or disabled at that moment, adds «(часть источников не отвечает —
  данные неполные)».
- ⚙️ Source in SOURCE_ERROR for 3 consecutive runs: «X не отвечает»; recovery message when back.
- 📢 Telegram post with outage/recovery keywords: forwarded as quote + link; last seen post id stored.
- 💓 Daily heartbeat at 09:00 MSK: «я жив», source health.

Keywords: see `monitor/sources/telegram_channel.py`. Recovery only on finished forms
(«восстановлена», «устранён»), so «работаем над восстановлением» stays an outage.

Messages are clamped to 4000 characters. A message Telegram rejects with HTTP 400 is
logged and dropped (it can never succeed and would block every later alert); other
send failures fail the run and are retried.

`state.json` stores a source's details and link only while it reports `OUTAGE`, so
calm runs (whose DownRadar hourly count changes every time) don't rewrite the file.

## Error handling

- Timeout 15 s, one retry; honour `Retry-After` on 429; no retry on 401/403.
- Sources are isolated: one failure does not affect others.
- Telegram send failure (other than HTTP 400) fails the run; state is not saved, so the
  alert retries next run.

## Layout

```
.github/workflows/monitor.yml
monitor/sources/{detector404,downreport,downradar,telegram_channel}.py
monitor/{state,notifier,main}.py
tests/ (+ fixtures/*.html)
state.json, requirements.txt, README.md
```

## Testing

- Parsers: saved HTML fixtures (ok + outage variants).
- Transitions: unit tests without network.
- `workflow_dispatch` input `test_message` sends a test message.
