# Собирает SVG для профиля: шапку и карточки проектов, светлую и тёмную версии.
# Стиль как на rooni.dev: монохром, соединённые плитки, DM Sans / DM Mono.
# Запуск: python scripts/build.py (нужен fonttools). Данные берёт из публичного API GitHub.
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
USER = "YouRooni"

HERO = {
    "name": "Rooni",
    "lines": [
        "Developer and a bit of a designer.",
        "Разработчик и немного дизайнер.",
    ],
    "buttons": [("Telegram", True), ("rooni.dev", False)],
}

PROJECTS = [
    {"repo": "Maxli", "icon": "smart_toy", "shape": "cookie-12",
     "desc": "Userbot for the MAX messenger: automation and custom scripts."},
    {"repo": "Wallify-Repo", "title": "Wallify", "icon": "wallpaper", "shape": "cookie-6",
     "desc": "Android app for live wallpapers in HTML, CSS and JS."},
    {"repo": "AovoControl", "icon": "electric_scooter", "shape": "cookie-9",
     "desc": "Control AOVO e-scooters over Bluetooth: speed, lights, settings."},
    {"repo": "plugins", "title": "exteraGram plugins", "icon": "extension", "shape": "cookie-7",
     "desc": "Plugins for exteraGram and other Telegram clients."},
]

# Токены rooni.dev. Плитка в светлой чуть темнее, иначе теряется на белом фоне GitHub
THEMES = {
    "dark": {
        "tile": "#1d1d1d", "pill": "#303030", "dots": "#e6e6e6",
        "primary": "#e4e4e4", "on_primary": "#181818",
        "text": "#e6e6e6", "variant": "#a8a8a8", "muted": "#7b7b7b",
    },
    "light": {
        "tile": "#f2f2f2", "pill": "#e2e2e2", "dots": "#1a1a1a",
        "primary": "#1c1c1c", "on_primary": "#f4f4f4",
        "text": "#1a1a1a", "variant": "#5d5d5d", "muted": "#8a8a8a",
    },
}

OUTER, INNER = 26, 6


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

    def width(self, text, size, spacing=0):
        units = 0
        for ch in text:
            g = self.cmap.get(ord(ch))
            units += self.hmtx[g][0] if g else self.upm * 0.5
        return units * size / self.upm + spacing * len(text)

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


# --- формы и иконки -------------------------------------------------------

def path_of(folder, name):
    svg = (ROOT / folder / f"{name}.svg").read_text(encoding="utf-8")
    return re.search(r'\bd="([^"]+)"', svg).group(1)


def icon(name, x, y, size, color):
    # Material Symbols рисуются в системе 0..960 со сдвигом -960 по Y
    k = size / 960
    return (f'<path transform="translate({x} {y + size}) scale({k})" '
            f'd="{path_of("icons", name)}" fill="{color}"/>')


def shape(name, x, y, size, color):
    k = size / 100
    return f'<path transform="translate({x} {y}) scale({k})" d="{path_of("shapes", name)}" fill="{color}"/>'


def rect(x, y, w, h, tl, tr, br, bl):
    # Прямоугольник с отдельным радиусом на каждый угол
    return (f"M{x + tl},{y}H{x + w - tr}A{tr},{tr} 0 0 1 {x + w},{y + tr}"
            f"V{y + h - br}A{br},{br} 0 0 1 {x + w - br},{y + h}"
            f"H{x + bl}A{bl},{bl} 0 0 1 {x},{y + h - bl}"
            f"V{y + tl}A{tl},{tl} 0 0 1 {x + tl},{y}Z")


def svg_doc(w, h, label, css, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}">'
            f'<title>{escape(label)}</title><style>{css}</style>{body}</svg>')


# --- шапка ---------------------------------------------------------------

def hero(theme, avatar_uri):
    t = THEMES[theme]
    w, h = 840, 300
    name, lines, buttons = HERO["name"], HERO["lines"], HERO["buttons"]

    # Пара кнопок как hero-cta на сайте: у стыка 6px, снаружи 24px
    bx, by, bh, btn_svg = 40, 216, 48, []
    for i, (label, filled) in enumerate(buttons):
        tw = SEMIBOLD.width(label, 15)
        bw = tw + 48 + (26 if filled else 0)
        rl = 24 if i == 0 else INNER
        rr = 24 if i == len(buttons) - 1 else INNER
        fill = t["primary"] if filled else t["pill"]
        fg = t["on_primary"] if filled else t["text"]
        btn_svg.append(f'<path d="{rect(bx, by, bw, bh, rl, rr, rr, rl)}" fill="{fill}"/>'
                       f'<text x="{bx + 24}" y="{by + 29.5}" font-size="15" font-weight="600" '
                       f'fill="{fg}">{escape(label)}</text>')
        if filled:
            btn_svg.append(icon("arrow_outward", bx + 24 + tw + 8, by + 15, 18, fg))
        bx += bw + 3

    lines_svg = "".join(
        f'<text x="42" y="{160 + i * 26}" font-size="17" fill="{t["variant"]}">{escape(l)}</text>'
        for i, l in enumerate(lines))

    ava, size = 560, 240
    css = font_css("".join(lines), name + "".join(b for b, _ in buttons), "")
    body = (
        "<defs>"
        # Точечный «дизеринг» как фон rooni.dev, гаснет к правому краю
        '<pattern id="dots" width="6" height="6" patternUnits="userSpaceOnUse">'
        f'<rect width="2" height="2" fill="{t["dots"]}"/></pattern>'
        '<radialGradient id="fade" cx=".22" cy=".1" r=".8">'
        '<stop offset="0" stop-color="#fff" stop-opacity=".16"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="m"><rect width="{w}" height="{h}" fill="url(#fade)"/></mask>'
        f'<clipPath id="ava"><path transform="translate({ava} 30) scale({size / 100})" '
        f'd="{path_of("shapes", "squircle")}"/></clipPath>'
        "</defs>"
        f'<rect width="{w}" height="{h}" rx="{OUTER}" fill="{t["tile"]}"/>'
        f'<rect width="{w}" height="{h}" rx="{OUTER}" fill="url(#dots)" mask="url(#m)"/>'
        f'<text x="36" y="124" font-size="100" font-weight="600" letter-spacing="-4" '
        f'fill="{t["text"]}">{escape(name)}</text>'
        + lines_svg + "".join(btn_svg)
        + shape("squircle", ava, 30, size, t["pill"])
        + f'<image href="{avatar_uri}" x="{ava}" y="30" width="{size}" height="{size}" '
          'preserveAspectRatio="xMidYMid slice" clip-path="url(#ava)"/>'
    )
    return svg_doc(w, h, f"{name}. {lines[0]}", css, body)


# --- карточки проектов ----------------------------------------------------

def card(theme, p, info, corners):
    t = THEMES[theme]
    w, h = 416, 212
    title = p.get("title", p["repo"])
    lines = wrap(p["desc"], REGULAR, 14.5, w - 56)[:2]
    lang = info.get("language") or ""
    stars = info.get("stargazers_count", 0)
    chip = " · ".join(x for x in (lang, f"★ {stars}" if stars else "") if x) or "GitHub"

    desc_svg = "".join(
        f'<text x="28" y="{134 + i * 23}" font-size="14.5" fill="{t["variant"]}">{escape(l)}</text>'
        for i, l in enumerate(lines))

    css = font_css(p["desc"], title, chip)
    body = (
        f'<path d="{rect(0, 0, w, h, *corners)}" fill="{t["tile"]}"/>'
        + shape(p["shape"], 28, 28, 48, t["pill"])
        + icon(p["icon"], 40, 40, 24, t["text"])
        + icon("arrow_outward", w - 28 - 22, 41, 22, t["variant"])
        + f'<text x="28" y="106" font-size="19" font-weight="600" letter-spacing="-.38" '
          f'fill="{t["text"]}">{escape(title)}</text>'
        + desc_svg
        + f'<text class="m" x="28" y="{h - 26}" font-size="13" fill="{t["variant"]}">{escape(chip)}</text>'
    )
    return svg_doc(w, h, title, css, body)


def grid_corners(i, total, cols=2):
    # Сетка как одна группа: внешние углы 26px, на стыках 6px
    rows = (total + cols - 1) // cols
    r, c = divmod(i, cols)
    top, bottom = r == 0, r == rows - 1
    left, right = c == 0, c == cols - 1
    pick = lambda cond: OUTER if cond else INNER
    return (pick(top and left), pick(top and right), pick(bottom and right), pick(bottom and left))


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
    raw, ctype = fetch(f"https://avatars.githubusercontent.com/{USER}?s=480")
    avatar = f"data:{ctype.split(';')[0]};base64,{base64.b64encode(raw).decode()}"

    for theme in THEMES:
        (out / f"hero-{theme}.svg").write_text(hero(theme, avatar), encoding="utf-8")

    for i, p in enumerate(PROJECTS):
        info = repos.get(p["repo"], {})
        slug = p["repo"].lower()
        corners = grid_corners(i, len(PROJECTS))
        for theme in THEMES:
            (out / f"project-{slug}-{theme}.svg").write_text(card(theme, p, info, corners),
                                                             encoding="utf-8")
        print(f"{p['repo']}: {info.get('stargazers_count')} stars")


if __name__ == "__main__":
    main()
