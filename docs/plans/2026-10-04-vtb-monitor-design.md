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
| DETECTOR404 | API `GET /api/v1/service/{service}/status`, Bearer token | API reports a problem (response format to finalise once a token exists) |
| DownReport | HTML `https://downreport.ru/vtb` | Verdict text is not «Массовых жалоб нет» |
| DownRadar | HTML `https://downradar.ru/ne-rabotaet/vtb.ru` | «Статус Vtb.ru : есть проблемы» (detector compares to its own baseline) |
| Telegram @bankvtb | HTML `https://t.me/s/bankvtb` | New post matches outage keywords (official confirmation) |

Excluded:
- Downdetector: Cloudflare challenge, ToS forbids scraping; only the paid Enterprise API is legitimate.
- DownScope: no public VTB page.
- vtb.ru synthetic check: Russian root CA plus foreign GitHub IPs make it meaningless.
- CBR RSS: no outage info.

Parsers that cannot find the expected marker return `SOURCE_ERROR`, never `OK`.

## Alert rules (state transitions only)

- Crowd sources (DownReport, DownRadar) need `OUTAGE` on 2 consecutive runs.
  DETECTOR404 and Telegram posts count immediately.
- 🔴 First source enters OUTAGE: «ВТБ: возможный сбой», source, numbers, link, all-source summary.
- ➕ Another source joins during an incident: «сбой подтверждает X (N из M)».
- 🟢 All sources OK for 2 consecutive runs: «сбой завершён, длительность».
- ⚙️ Source in SOURCE_ERROR for 3 consecutive runs: «X не отвечает»; recovery message when back.
- 📢 Telegram post with outage/recovery keywords: forwarded as quote + link; last seen post id stored.
- 💓 Daily heartbeat at 09:00 MSK: «я жив», source health.

Keywords: «технические работы», «технический сбой», «затруднени», «временно недоступ»,
«не проходят», «не работает», «наблюдаются проблемы», «восстановлен», «проблема устранена».

## Error handling

- Timeout 15 s, one retry; honour `Retry-After` on 429; no retry on 401/403.
- Sources are isolated: one failure does not affect others.
- Telegram send failure fails the run; state is not saved, so the alert retries next run.

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
