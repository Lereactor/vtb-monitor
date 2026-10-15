"""One-page overview of the VTB outage notifier for a manager (A4 landscape)."""
import sys

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

registerFont(TTFont("R", "C:/Windows/Fonts/segoeui.ttf"))
registerFont(TTFont("B", "C:/Windows/Fonts/segoeuib.ttf"))

INK = HexColor("#1B2333")
MUTED = HexColor("#6B7385")
LINE = HexColor("#C9CFDB")
PANEL = HexColor("#F3F5F9")
VTB = HexColor("#0A2896")
RED = HexColor("#D93A3A")
ORANGE = HexColor("#E8892B")
BLUE = HexColor("#2F6FDE")
GREEN = HexColor("#2E9E5B")
GREY = HexColor("#8A93A6")
PINK = HexColor("#D9487A")

W, H = landscape(A4)
M = 30
c = canvas.Canvas(sys.argv[1], pagesize=(W, H))
c.setTitle("Оповещатель о сбоях ВТБ")


def text(x, y, s, font="R", size=10, color=INK, anchor="l"):
    c.setFont(font, size)
    c.setFillColor(color)
    {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[anchor](x, y, s)


def wrap(s, font, size, width):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if stringWidth(trial, font, size) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


def para(x, y, s, width, font="R", size=9, color=INK, lead=None, anchor="l"):
    lead = lead or size * 1.3
    for i, line in enumerate(wrap(s, font, size, width)):
        text(x, y - i * lead, line, font, size, color, anchor)
    return y - len(wrap(s, font, size, width)) * lead


def box(x, y, w, h, fill=white, stroke=LINE, r=8, lw=1):
    c.setFillColor(fill)
    c.setStrokeColor(stroke or fill)
    c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, stroke=1 if stroke else 0, fill=1)


def arrow(x1, y1, x2, y2, color=INK, lw=1.6, head=6):
    import math
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(lw)
    ang = math.atan2(y2 - y1, x2 - x1)
    bx, by = x2 - head * math.cos(ang), y2 - head * math.sin(ang)
    c.line(x1, y1, bx, by)
    p = c.beginPath()
    p.moveTo(x2, y2)
    for side in (1, -1):
        p.lineTo(bx + side * head * 0.6 * math.sin(ang), by - side * head * 0.6 * math.cos(ang))
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def badge(x, y, r, color, mark):
    """Coloured disc with a white drawn symbol (no emoji fonts in PDF)."""
    c.setFillColor(color)
    c.circle(x, y, r, stroke=0, fill=1)
    c.setStrokeColor(white)
    c.setFillColor(white)
    c.setLineWidth(r * 0.22)
    c.setLineCap(1)
    k = r * 0.45
    if mark == "!":
        c.line(x, y - k * 0.2, x, y + k)
        c.circle(x, y - k * 0.75, r * 0.12, stroke=0, fill=1)
    elif mark == "+":
        c.line(x - k, y, x + k, y)
        c.line(x, y - k, x, y + k)
    elif mark == "ok":
        p = c.beginPath()
        p.moveTo(x - k, y)
        p.lineTo(x - k * 0.25, y - k * 0.7)
        p.lineTo(x + k, y + k * 0.7)
        c.drawPath(p, stroke=1, fill=0)
    elif mark == "i":  # megaphone-ish: official statement
        c.line(x, y - k, x, y + k * 0.2)
        c.circle(x, y + k * 0.75, r * 0.12, stroke=0, fill=1)
    elif mark == "x":
        c.line(x - k * 0.8, y - k * 0.8, x + k * 0.8, y + k * 0.8)
        c.line(x - k * 0.8, y + k * 0.8, x + k * 0.8, y - k * 0.8)
    elif mark == "pulse":
        p = c.beginPath()
        p.moveTo(x - k * 1.2, y)
        for dx, dy in ((-0.5, 0), (-0.25, 0.8), (0.15, -0.8), (0.45, 0), (1.2, 0)):
            p.lineTo(x + k * dx, y + k * dy)
        c.drawPath(p, stroke=1, fill=0)
    c.setLineCap(0)


# ---------- header ----------
c.setFillColor(VTB)
c.rect(0, H - 78, W, 78, stroke=0, fill=1)
text(M, H - 42, "Оповещатель о сбоях ВТБ", "B", 24, white)
text(M, H - 63, "Следит 24/7 за ВТБ Бизнес-онлайн и Мои Инвестиции, пишет в Telegram", "R", 12, HexColor("#CFD8F5"))
SITE = "lereactor.github.io/vtb-monitor-live"
text(W - M, H - 36, "Сайт: статус сейчас, все сбои, аналитика", "R", 9, HexColor("#CFD8F5"), "r")
text(W - M, H - 52, SITE, "B", 12, white, "r")
c.linkURL("https://" + SITE + "/", (W - M - stringWidth(SITE, "B", 12), H - 56, W - M, H - 40), relative=0)

# key numbers strip
stats = [("2 сервиса", "Бизнес-онлайн и Мои Инвестиции"),
         ("каждые 5 мин", "автоматическая проверка"),
         ("3 сайта жалоб", "+ канал ВТБ + доступность сайтов"),
         ("5–10 мин", "от всплеска жалоб до оповещения")]
sw = (W - 2 * M - 3 * 12) / 4
for i, (big, small) in enumerate(stats):
    x = M + i * (sw + 12)
    box(x, H - 132, sw, 44, PANEL, None)
    text(x + 14, H - 108, big, "B", 16, VTB)
    text(x + 14, H - 124, small, "R", 9, MUTED)

# ---------- how it works ----------
top = H - 150
text(M, top, "КАК РАБОТАЕТ", "B", 10, MUTED)
fh = 168
fy = top - 14 - fh  # bottom of flow area
mid = fy + fh / 2 + 10  # shared centre line of the flow boxes

VTB_CHIP, INV_CHIP = (VTB, "Бизнес"), (HexColor("#0F8B7E"), "Инвест.")


def chip(x, y, spec):
    """Small filled label; returns its width."""
    color, label = spec
    w = stringWidth(label, "B", 6.5) + 8
    c.setFillColor(color)
    c.roundRect(x, y, w, 10, 3, stroke=0, fill=1)
    text(x + 4, y + 3, label, "B", 6.5, white)
    return w


# sources column
srcs = [("DownReport", "жалобы пользователей", [VTB_CHIP, INV_CHIP]),
        ("DownRadar", "жалобы пользователей", [VTB_CHIP, INV_CHIP]),
        ("DETECTOR404", "флаг «много жалоб»", [INV_CHIP]),
        ("Сайты банка", "из России и мира", [VTB_CHIP, INV_CHIP])]
sx, sw_, sh, gap = M, 172, 26, 6
for i, (name, sub, chips) in enumerate(srcs):
    y = fy + fh - (i + 1) * sh - i * gap
    box(sx, y, sw_, sh, white, LINE, 5)
    text(sx + 9, y + 15, name, "B", 9)
    text(sx + 9, y + 5, sub, "R", 7, MUTED)
    cx = sx + sw_ - 6
    for spec in reversed(chips):
        cx -= stringWidth(spec[1], "B", 6.5) + 8
        chip(cx, y + 8, spec)
        cx -= 3
# chip legend next to the section title
lx0 = M + 112
lx0 += chip(lx0, top - 2, VTB_CHIP) + 4
text(lx0, top, "ВТБ Бизнес-онлайн (db.vtb.ru)", "R", 8, MUTED)
lx0 += stringWidth("ВТБ Бизнес-онлайн (db.vtb.ru)", "R", 8) + 12
lx0 += chip(lx0, top - 2, INV_CHIP) + 4
text(lx0, top, "ВТБ Мои Инвестиции", "R", 8, MUTED)
cy_src = fy + fh - 2 * sh - 1.5 * gap
oy = fy + 2
box(sx, oy, sw_, sh, HexColor("#E8EEFC"), BLUE, 5)
text(sx + 9, oy + 15, "Канал @bankvtb", "B", 9, BLUE)
text(sx + 9, oy + 5, "официальные посты", "R", 7, MUTED)
chip(sx + sw_ - 6 - (stringWidth("Инвест.", "B", 6.5) + 8) - 3 - (stringWidth("Бизнес", "B", 6.5) + 8),
     oy + 8, VTB_CHIP)
chip(sx + sw_ - 6 - (stringWidth("Инвест.", "B", 6.5) + 8), oy + 8, INV_CHIP)

# server
vx, vw = 244, 180
vh = 104
vy = mid - vh / 2
box(vx, vy, vw, vh, PANEL, None)
text(vx + 12, vy + vh - 20, "Сервер (Россия)", "B", 11)
para(vx + 12, vy + vh - 36, "раз в 5 минут проверяет оба сервиса и решает: сбой или нет", vw - 24,
     size=8.5, color=MUTED)
para(vx + 12, vy + 26, "ложные тревоги отсекает: 2 проверки подряд; сайты банка — доп. показатель, без тревог", vw - 24, size=8,
     color=MUTED)
arrow(sx + sw_ + 4, mid, vx - 4, mid, INK)

# github
gx, gw = 478, 140
gh = 84
gy = mid - gh / 2
box(gx, gy, gw, gh, PANEL, None)
text(gx + 12, gy + gh - 20, "GitHub", "B", 11)
para(gx + 12, gy + gh - 36, "доставляет сообщения в Telegram и читает канал банка", gw - 24, size=8.5,
     color=MUTED)
arrow(vx + vw + 4, mid, gx - 4, mid, INK)
text((vx + vw + gx) / 2, mid + 7, "тревога", "R", 7.5, MUTED, "c")
c.setStrokeColor(BLUE)
c.setLineWidth(1.6)
c.line(sx + sw_ + 4, oy + sh / 2, gx + gw / 2, oy + sh / 2)
arrow(gx + gw / 2, oy + sh / 2, gx + gw / 2, gy - 4, BLUE)
text(vx + vw / 2, oy + sh / 2 + 6, "новые посты банка", "R", 7.5, BLUE, "c")

# telegram channel
tx, tw = 680, W - M - 680
th = 116
ty = mid - th / 2
box(tx, ty, tw, th, HexColor("#E7F4FB"), HexColor("#2AABEE"), lw=1.4)
text(tx + 12, ty + th - 22, "Telegram-канал", "B", 11, HexColor("#147FB8"))
text(tx + 12, ty + th - 36, "оповещений", "B", 11, HexColor("#147FB8"))
para(tx + 12, ty + th - 54, "Руководитель и команда видят сообщение на телефоне", tw - 24, size=8.5,
     color=MUTED)
for i in range(3):  # people
    px, py = tx + 22 + i * 22, ty + 16
    c.setFillColor(HexColor("#2AABEE"))
    c.circle(px, py + 10, 5, stroke=0, fill=1)
    c.wedge(px - 9, py - 7, px + 9, py + 11, 0, 180, stroke=0, fill=1)
arrow(gx + gw + 4, mid, tx - 4, mid, INK)
text((gx + gw + tx) / 2, mid + 7, "≈1 мин", "R", 7.5, MUTED, "c")

# ---------- example timeline ----------
by = 28  # bottom margin
tl_top = fy - 22
lw_ = 520
text(M, tl_top, "ПРИМЕР: СБОЙ ВТБ БИЗНЕС-ОНЛАЙН (условные время и цифры)", "B", 10, MUTED)
text(M, tl_top - 13, "Сбой Мои Инвестиции идёт своей цепочкой сообщений, там подтверждение — «2 из 3»",
     "R", 8.5, MUTED)
ly = (tl_top + by) / 2 + 4  # timeline axis
x0, x1 = M + 48, M + lw_
t0, t1 = 0, 75  # minutes from 10:00 to 11:15


def tx_(minute):
    return x0 + (x1 - x0) * (minute - t0) / (t1 - t0)


c.setStrokeColor(LINE)
c.setLineWidth(2)
c.line(x0, ly, x1, ly)
arrow(x1 - 10, ly, x1 + 6, ly, LINE, 2)

events = [  # minute, time, color, mark, title, sub, above
    (0, "10:00", GREY, None, "Клиенты жалуются", "на сайтах жалоб", True),
    (5, "10:05", RED, "!", "Похоже на сбой", "видит 1 сайт из 2", False),
    (15, "10:15", ORANGE, "+", "Подтверждение", "видят 2 сайта из 2", True),
    (27, "10:27", BLUE, "i", "ВТБ официально", "«наблюдаются затруднения»", False),
    (60, "11:00", GREY, None, "Жалобы стихли", "", True),
    (70, "11:10", GREEN, "ok", "Всё в норме", "сбой длился 1 ч 05 мин", False),
]
for minute, hm, color, mark, title, sub, above in events:
    x = tx_(minute)
    if mark:
        badge(x, ly, 9, color, mark)
    else:
        c.setFillColor(white)
        c.setStrokeColor(GREY)
        c.setLineWidth(2)
        c.circle(x, ly, 5, stroke=1, fill=1)
    text(x, ly - 22 if above else ly + 14, hm, "B", 9, color if mark else MUTED, "c")
    ty0 = ly + 46 if above else ly - 42
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(x, ly + (12 if above else -12), x, ty0 + (-4 if above else 10))
    text(x, ty0, title, "B", 9, INK, "c")
    if sub:
        text(x, ty0 - 11, sub, "R", 7.5, MUTED, "c")


def bracket(m1, m2, y, label):
    a, b = tx_(m1), tx_(m2)
    c.setStrokeColor(RED)
    c.setLineWidth(1)
    c.line(a, y, b, y)
    c.line(a, y - 3, a, y + 3)
    c.line(b, y - 3, b, y + 3)
    text((a + b) / 2, y - 10, label, "B", 7.5, RED, "c")


bracket(0, 5, ly - 72, "реакция 5–10 мин")
bracket(60, 70, ly + 76, "10 мин: проверяем, что точно ок")

# ---------- message legend ----------
lx = M + lw_ + 40
lwid = W - M - lx
box(lx - 14, by - 4, lwid + 14, tl_top - by + 12, PANEL, None)
text(lx, tl_top - 8, "ЧТО ПРИХОДИТ В КАНАЛ", "B", 10, MUTED)
text(lx, tl_top - 22, "в начале — сервис: Бизнес-онлайн или Мои Инвестиции", "R", 8, MUTED)
legend = [
    (RED, "!", "Похоже на сбой", "цифры, ссылка, открываются ли сайты банка"),
    (ORANGE, "+", "Сбой подтверждает ещё сайт", "«2 из 2»: тем вероятнее сбой"),
    (BLUE, "i", "ВТБ официально сообщает", "пост из канала банка"),
    (GREEN, "ok", "Всё в норме", "сбой закончился, с длительностью"),
    (GREY, "x", "Сайт не отвечает 30 мин", "не сбой банка; статус всех проверок"),
    (PINK, "pulse", "Утренний отчёт в 9:00", "нет отчёта = сломался оповещатель"),
]
ry = tl_top - 44
for color, mark, title, sub in legend:
    badge(lx + 10, ry - 3, 9, color, mark)
    text(lx + 28, ry, title, "B", 9.5)
    text(lx + 28, ry - 11, sub, "R", 8, MUTED)
    ry -= 29

# footer note
badge(M + 6, by + 6, 6, BLUE, "i")
text(M + 18, by + 3, "Жалобы клиентов — ранний сигнал, но не доказательство. Подтверждённый сбой — только сообщение от банка.", "R", 8.5, MUTED)

c.showPage()
c.save()
