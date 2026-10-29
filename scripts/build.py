# Собирает SVG для профиля: шапку, плитки-ссылки и карточки проектов, светлую и тёмную версии.
# Стиль как на rooni.dev: монохром, соединённые плитки, DM Sans / DM Mono,
# формы M3E из shapes.js и пиксельный Bayer-фон из bgFx.js.
# Запуск: python scripts/build.py (нужны fonttools и pillow). Данные берёт из публичного API GitHub.
import base64
import io
import json
import math
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image

import shapes

ROOT = Path(__file__).resolve().parent.parent
USER = "YouRooni"

HERO = {
    "name": "Rooni",
    "lines": [
        "Developer and a bit of a designer.",
        "Разработчик и немного дизайнер.",
    ],
    "stack": ["Kotlin", "Python", "Java", "TypeScript"],
}

LINKS = [
    {"slug": "telegram", "icon": "send", "shape": "cookie6", "hover": "sunny",
     "label": "Telegram", "value": "@YouRooni"},
    {"slug": "channel", "icon": "campaign", "shape": "cookie9", "hover": "flower",
     "label": "Channel", "value": "@RnPlugins"},
    {"slug": "site", "icon": "language", "shape": "cookie4", "hover": "clover4",
     "label": "Website", "value": "rooni.dev"},
]

PROJECTS = [
    {"repo": "Maxli", "icon": "smart_toy", "shape": "cookie12", "hover": "burst",
     "desc": "Userbot for the MAX messenger: automation and custom scripts."},
    {"repo": "Wallify-Repo", "title": "Wallify", "icon": "wallpaper", "shape": "cookie6", "hover": "sunny",
     "desc": "Android app for live wallpapers in HTML, CSS and JS."},
    {"repo": "AovoControl", "icon": "electric_scooter", "shape": "cookie9", "hover": "flower",
     "desc": "Control AOVO e-scooters over Bluetooth: speed, lights, settings."},
    {"repo": "plugins", "title": "exteraGram plugins", "icon": "extension", "shape": "cookie4", "hover": "clover4",
     "desc": "Plugins for exteraGram and other Telegram clients."},
]

# Токены rooni.dev. Плитка в светлой чуть темнее, иначе теряется на белом фоне GitHub
THEMES = {
    "dark": {
        "tile": "#1d1d1d", "pill": "#303030", "primary": (228, 228, 228), "fx": 0.11,
        "text": "#e6e6e6", "variant": "#a8a8a8", "muted": "#7b7b7b",
    },
    "light": {
        "tile": "#f2f2f2", "pill": "#e2e2e2", "primary": (28, 28, 28), "fx": 0.07,
        "text": "#1a1a1a", "variant": "#5d5d5d", "muted": "#8a8a8a",
    },
}

OUTER, INNER = 26, 6
LOOP = 9  # секунд, общий цикл всех анимаций
REDUCE = "@media (prefers-reduced-motion:reduce){.fx-a{display:none}.fx-s{display:inline}}"


def api(path):
    req = urllib.request.Request(f"https://api.github.com/{path}",
                                 headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read(), r.headers.get("Content-Type", "image/png")


# --- шрифты ---------------------------------------------------------------

class Font:
    # Статичный срез DM Sans нужного веса: для замеров текста и для встраивания
    def __init__(self, path, wght=None):
        f = TTFont(path)
        if wght is not None:
            f = instancer.instantiateVariableFont(f, {"wght": wght, "opsz": 14})
        self.font = f
        self.upm = f["head"].unitsPerEm
        self.cmap = f.getBestCmap()
        self.hmtx = f["hmtx"]

    def width(self, text, size):
        units = 0
        for ch in text:
            g = self.cmap.get(ord(ch))
            units += self.hmtx[g][0] if g else self.upm * 0.5
        return units * size / self.upm

    def woff(self, text):
        # Режем шрифт до нужных букв, woff на zlib (brotli не нужен)
        buf = io.BytesIO()
        self.font.save(buf)
        buf.seek(0)
        f = TTFont(buf)
        opts = subset.Options()
        opts.flavor = "woff"
        opts.layout_features = ["kern", "liga"]
        sub = subset.Subsetter(opts)
        sub.populate(text=text + " ")
        sub.subset(f)
        out = io.BytesIO()
        f.flavor = "woff"
        f.save(out)
        return base64.b64encode(out.getvalue()).decode()


SANS = ROOT / "fonts" / "DMSans.ttf"
MONO = ROOT / "fonts" / "DMMono-Medium.ttf"
REGULAR = Font(SANS, 400)
SEMIBOLD = Font(SANS, 600)
MONO_F = Font(MONO)


def font_css(reg, semi, mono):
    return (
        f"@font-face{{font-family:S;font-weight:400;src:url(data:font/woff;base64,{REGULAR.woff(reg)})}}"
        f"@font-face{{font-family:S;font-weight:600;src:url(data:font/woff;base64,{SEMIBOLD.woff(semi)})}}"
        f"@font-face{{font-family:M;src:url(data:font/woff;base64,{MONO_F.woff(mono)})}}"
        "text{font-family:S,'DM Sans',system-ui,sans-serif}"
        ".m{font-family:M,'DM Mono',ui-monospace,monospace}"
    )


def wrap(text, font, size, max_w):
    lines, cur = [], ""
    for word in text.split():
        probe = f"{cur} {word}".strip()
        if font.width(probe, size) <= max_w or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# --- примитивы ------------------------------------------------------------

def icon(name, x, y, size, color):
    # Material Symbols рисуются в системе 0..960 со сдвигом -960 по Y
    svg = (ROOT / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    d = re.search(r'\bd="([^"]+)"', svg).group(1)
    return f'<path transform="translate({x} {y + size}) scale({size / 960})" d="{d}" fill="{color}"/>'


def rect(x, y, w, h, tl, tr, br, bl):
    # Прямоугольник с отдельным радиусом на каждый угол
    return (f"M{x + tl},{y}H{x + w - tr}A{tr},{tr} 0 0 1 {x + w},{y + tr}"
            f"V{y + h - br}A{br},{br} 0 0 1 {x + w - br},{y + h}"
            f"H{x + bl}A{bl},{bl} 0 0 1 {x},{y + h - bl}"
            f"V{y + tl}A{tl},{tl} 0 0 1 {x + tl},{y}Z")


def morph_pill(base, hover, x, y, size, color, begin):
    # Подложка иконки дышит как на сайте при наведении: base -> hover с пружиной и обратно
    turn = math.pi / 6
    frames = [(0, 0), (.34, 0), (.42, 1.12), (.47, 1), (.84, 1), (.91, -.06), (.96, 0), (1, 0)]
    values = ";".join(shapes.blend(base, hover, t, x, y, size, turn * max(0, min(t, 1)))
                      for _, t in frames)
    times = ";".join(str(k) for k, _ in frames)
    splines = ";".join([".3 0 .2 1"] * (len(frames) - 1))
    return (f'<path d="{shapes.blend(base, hover, 0, x, y, size)}" fill="{color}">'
            f'<animate attributeName="d" dur="{LOOP}s" begin="{begin}s" repeatCount="indefinite" '
            f'calcMode="spline" keyTimes="{times}" keySplines="{splines}" values="{values}"/></path>')


def svg_doc(w, h, label, css, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}">'
            f'<title>{escape(label)}</title><style>{css}</style>{body}</svg>')


def corners_for(row, col, rows, cols):
    # Группа плиток: внешние углы 26px, на стыках 6px
    pick = lambda cond: OUTER if cond else INNER
    top, bottom, left, right = row == 0, row == rows - 1, col == 0, col == cols - 1
    return (pick(top and left), pick(top and right), pick(bottom and right), pick(bottom and left))


# --- пиксельный фон -------------------------------------------------------

BAYER = [(v + .5) / 16 for v in (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)]
LEVELS = 5
CELL = 5
FRAMES = 36


def _smooth(a, b, x):
    t = min(1, max(0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def _hash(x, y, s):
    h = (x * 374761393 + y * 668265263 + s * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) / 4294967295


def dither_frames(w, h, rgb, alpha):
    # Тот же «дым» из трёх блобов, что в hero на rooni.dev, только зациклен по фазе
    gw, gh = math.ceil(w / CELL), math.ceil(h / CELL)
    aspect = gw / gh
    out = []
    for f in range(FRAMES):
        th = f / FRAMES * math.tau
        b1x, b1y = aspect * (.8 + .05 * math.sin(th)), .2 + .05 * math.cos(th)
        b2x, b2y = aspect * (.12 + .05 * math.sin(th + 1)), .5 + .05 * math.cos(2 * th)
        b3x = aspect * (.5 + .06 * math.sin(th + 2))
        img = Image.new("RGBA", (gw, gh))
        px = img.load()
        for y in range(gh):
            Y = y / gh
            row = 1 - _smooth(.3, 1, Y)
            for x in range(gw):
                X = x / gw * aspect
                hv = max(0, math.exp(-((X - b1x) ** 2 + (Y - b1y) ** 2) / .3)
                         + .7 * math.exp(-((X - b2x) ** 2 + (Y - b2y) ** 2) / .25)
                         + .5 * math.exp(-((X - b3x) ** 2 + Y ** 2) / .2)
                         + .07 * math.sin(X * 7 + Y * 4 + th)) * row
                q = math.floor(min(1.25, hv) * LEVELS + BAYER[(y & 3) * 4 + (x & 3)])
                a = min(q, LEVELS * 1.25) / LEVELS * alpha
                # Редкий «иней»: пиксели вспыхивают и гаснут, два цикла за петлю
                cyc = 2 * f / FRAMES + _hash(x, y, 1)
                cycle = math.floor(cyc)
                if row > .05 and _hash(x, y, 7 + cycle % 2) > .985:
                    a += .6 * alpha * math.sin(math.pi * (cyc - cycle)) ** 2 * row
                px[x, y] = (*rgb, round(min(1, a) * 255))
        # Кадр храним в размер сетки, растягивает браузер без сглаживания (image-rendering)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        out.append("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode())
    return out, gw * CELL, gh * CELL


# --- шапка ---------------------------------------------------------------

def hero(theme, avatar_uri):
    t = THEMES[theme]
    w, h = 840, 280
    name, lines, stack = HERO["name"], HERO["lines"], HERO["stack"]

    frames, fw, fh = dither_frames(w, h, t["primary"], t["fx"])
    n = len(frames)
    fx = []
    for i, uri in enumerate(frames):
        vals = ";".join("1" if k == i else "0" for k in range(n))
        fx.append(f'<image class="px" href="{uri}" preserveAspectRatio="none" width="{fw}" height="{fh}" opacity="{1 if i == 0 else 0}">'
                  f'<animate attributeName="opacity" dur="{LOOP}s" repeatCount="indefinite" '
                  f'calcMode="discrete" values="{vals}"/></image>')

    lines_svg = "".join(
        f'<text x="42" y="{150 + i * 26}" font-size="17" fill="{t["variant"]}">{escape(l)}</text>'
        for i, l in enumerate(lines))

    # Стек соединёнными чипами: снаружи 16px, на стыках 5px
    cx, chips = 40, []
    for i, s in enumerate(stack):
        cw = MONO_F.width(s, 13) + 28
        rl = 16 if i == 0 else 5
        rr = 16 if i == len(stack) - 1 else 5
        chips.append(f'<path d="{rect(cx, 202, cw, 34, rl, rr, rr, rl)}" fill="{t["pill"]}"/>'
                     f'<text class="m" x="{cx + 14}" y="223.5" font-size="13" fill="{t["variant"]}">{s}</text>')
        cx += cw + 3

    # Ава как на сайте: скругление 30%, по циклу становится кругом и чуть поворачивается
    ax, ay, size = 590, 30, 220
    r0, r1 = size * .3, size / 2
    c = (ax + size / 2, ay + size / 2)
    ava = (
        f'<clipPath id="ava"><rect x="{ax}" y="{ay}" width="{size}" height="{size}" rx="{r0}">'
        f'<animate attributeName="rx" dur="{LOOP}s" repeatCount="indefinite" calcMode="spline" '
        f'keyTimes="0;.5;.57;.9;.96;1" keySplines=".3 0 .2 1;.3 0 .2 1;.3 0 .2 1;.3 0 .2 1;.3 0 .2 1" '
        f'values="{r0};{r0};{r1};{r1};{r0};{r0}"/></rect></clipPath>'
    )
    rot = (f'<animateTransform attributeName="transform" type="rotate" dur="{LOOP}s" '
           f'repeatCount="indefinite" calcMode="spline" keyTimes="0;.5;.56;.6;.9;.95;.98;1" '
           f'keySplines="{";".join([".3 0 .2 1"] * 7)}" '
           f'values="0 {c[0]} {c[1]};0 {c[0]} {c[1]};-5.5 {c[0]} {c[1]};-4 {c[0]} {c[1]};'
           f'-4 {c[0]} {c[1]};1 {c[0]} {c[1]};0 {c[0]} {c[1]};0 {c[0]} {c[1]}"/>')

    css = (font_css("".join(lines), name, "".join(stack)) + ".fx-s{display:none}" + REDUCE
           + "image.px{image-rendering:crisp-edges;image-rendering:pixelated}")
    body = (
        f'<defs><clipPath id="tile"><rect width="{w}" height="{h}" rx="{OUTER}"/></clipPath>{ava}</defs>'
        f'<rect width="{w}" height="{h}" rx="{OUTER}" fill="{t["tile"]}"/>'
        f'<g clip-path="url(#tile)">'
        f'<g class="fx-a">{"".join(fx)}</g>'
        f'<image class="fx-s px" href="{frames[0]}" preserveAspectRatio="none" width="{fw}" height="{fh}"/></g>'
        f'<text x="36" y="118" font-size="100" font-weight="600" letter-spacing="-4" '
        f'fill="{t["text"]}">{escape(name)}</text>'
        + lines_svg + "".join(chips)
        + f'<g>{rot}<g clip-path="url(#ava)">'
          f'<rect x="{ax}" y="{ay}" width="{size}" height="{size}" fill="#fff"/>'
          f'<image href="{avatar_uri}" x="{ax}" y="{ay}" width="{size}" height="{size}" '
          'preserveAspectRatio="xMidYMid slice"/></g></g>'
    )
    return svg_doc(w, h, f"{name}. {lines[0]}", css, body)


# --- плитки-ссылки -------------------------------------------------------

def link_tile(theme, link, i, total):
    t = THEMES[theme]
    w, h = 276, 84
    css = font_css(link["label"], link["value"], "")
    body = (
        f'<path d="{rect(0, 0, w, h, *corners_for(0, i, 1, total))}" fill="{t["tile"]}"/>'
        + morph_pill(link["shape"], link["hover"], 20, 20, 44, t["pill"], i * .5)
        + icon(link["icon"], 31, 31, 22, t["text"])
        + f'<text x="80" y="37" font-size="12.5" fill="{t["muted"]}">{escape(link["label"])}</text>'
        + f'<text x="80" y="58" font-size="15.5" font-weight="600" fill="{t["text"]}">{escape(link["value"])}</text>'
        + icon("arrow_outward", w - 22 - 20, 31, 20, t["variant"])
    )
    return svg_doc(w, h, f'{link["label"]}: {link["value"]}', css, body)


# --- карточки проектов ----------------------------------------------------

def card(theme, p, info, i, total):
    t = THEMES[theme]
    w, h = 416, 212
    title = p.get("title", p["repo"])
    lines = wrap(p["desc"], REGULAR, 14.5, w - 56)[:2]
    lang = info.get("language") or ""
    stars = info.get("stargazers_count", 0)
    chip = " · ".join(x for x in (lang, f"★ {stars}" if stars else "") if x) or "GitHub"

    desc_svg = "".join(
        f'<text x="28" y="{134 + k * 23}" font-size="14.5" fill="{t["variant"]}">{escape(l)}</text>'
        for k, l in enumerate(lines))

    row, col = divmod(i, 2)
    css = font_css(p["desc"], title, chip)
    body = (
        f'<path d="{rect(0, 0, w, h, *corners_for(row, col, (total + 1) // 2, 2))}" fill="{t["tile"]}"/>'
        + morph_pill(p["shape"], p["hover"], 26, 26, 52, t["pill"], 1.5 + i * .5)
        + icon(p["icon"], 40, 40, 24, t["text"])
        + icon("arrow_outward", w - 28 - 22, 41, 22, t["variant"])
        + f'<text x="28" y="106" font-size="19" font-weight="600" letter-spacing="-.38" '
          f'fill="{t["text"]}">{escape(title)}</text>'
        + desc_svg
        + f'<text class="m" x="28" y="{h - 26}" font-size="13" fill="{t["variant"]}">{escape(chip)}</text>'
    )
    return svg_doc(w, h, title, css, body)


def main():
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.svg"):
        old.unlink()

    # Один запрос на все репо; если API отвалился (лимит), берём прошлый ответ
    cache = ROOT / "tmp" / "repos.json"
    try:
        repos = {r["name"]: r for r in api(f"users/{USER}/repos?per_page=100")}
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps(repos), encoding="utf-8")
    except urllib.error.HTTPError as e:
        print(f"API: {e}, using cache")
        repos = json.loads(cache.read_text(encoding="utf-8"))

    # Аватарку отдаёт CDN без лимитов, ссылка не меняется при смене авы
    raw, ctype = fetch(f"https://avatars.githubusercontent.com/{USER}?s=440")
    avatar = f"data:{ctype.split(';')[0]};base64,{base64.b64encode(raw).decode()}"

    def save(name, svg):
        (out / name).write_text(svg, encoding="utf-8")

    for theme in THEMES:
        save(f"hero-{theme}.svg", hero(theme, avatar))
        for i, link in enumerate(LINKS):
            save(f"link-{link['slug']}-{theme}.svg", link_tile(theme, link, i, len(LINKS)))
        for i, p in enumerate(PROJECTS):
            info = repos.get(p["repo"], {})
            save(f"project-{p['repo'].lower()}-{theme}.svg", card(theme, p, info, i, len(PROJECTS)))

    for f in sorted(out.glob("*.svg")):
        print(f"{f.name}: {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
