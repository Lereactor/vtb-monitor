from monitor import weekly


def public(summary="За 7 дней: 1 сбой Бизнес-онлайн (40 мин)."):
    return {"generated_at": "2026-10-26T06:05:00+00:00", "analytics": {"7d|all": {"summary": summary}}}


def test_caption_has_dates_summary_and_link():
    text = weekly.caption(public())
    assert text.startswith("📊 Сбои ВТБ за неделю 19.10–26.10\n\nЗа 7 дней: 1 сбой Бизнес-онлайн (40 мин).")
    assert text.endswith("Подробнее: https://lereactor.github.io/vtb-monitor-live/#tab=analytics&s=all&p=7d")


def test_long_summary_is_cut_to_the_caption_limit():
    text = weekly.caption(public("слово " * 400))
    assert len(text) <= weekly.MAX_CAPTION and "…\n\nПодробнее:" in text


def test_send_photo_posts_the_file(tmp_path):
    png = tmp_path / "w.png"
    png.write_bytes(b"\x89PNG")
    calls = []

    class Session:
        def post(self, url, data=None, files=None, timeout=None):
            calls.append((url, data, files["photo"][0]))

            class Resp:
                status_code = 200
                text = ""
            return Resp()

    weekly.send_photo("tok", "-100", png, "подпись", Session())
    assert calls == [("https://api.telegram.org/bottok/sendPhoto", {"chat_id": "-100", "caption": "подпись"},
                      "vtb-week.png")]
