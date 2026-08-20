#!/usr/bin/env python3
"""Сборка самодостаточного HTML-дека из фрагмента слайдов и brand.json.

    python3 build_deck.py slides.html --brand brand-kit/brand.json --out deck.html

На входе — только <section class="slide">…</section> подряд, без обвязки.
Скрипт добавляет дизайн-систему с токенами вашего бренда, встраивает шрифты и
картинки в base64 и вкладывает навигацию. На выходе один файл, который
открывается без интернета и уходит письмом.
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")

# Слайд PowerPoint шириной 13.333" = 960pt, поэтому 1pt ровно 0.10417vw.
# Благодаря этому кегли из разобранных презентаций переносятся один в один.
PT_TO_VW = 100.0 / 960.0
PX_AT_1600 = 1600.0 / 960.0

ICONS = {
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V6z"/>',
    "chart": '<path d="M3 17l6-6 4 4 8-8"/><path d="M17 7h4v4"/>',
    "bolt": '<path d="M13 2L4 14h6l-1 8 9-12h-6z"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="M16 6.5a3 3 0 0 1 0 6M21 20c0-2.8-1.7-5-4-5.7"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "check": '<path d="M4 12.5l5 5L20 6.5"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "lock": '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.6 2.7 2.6 15.3 0 18M12 3c-2.6 2.7-2.6 15.3 0 18"/>',
    "server": '<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/>',
    "doc": '<path d="M7 3h8l4 4v14H7z"/><path d="M15 3v4h4"/><path d="M10 12h7M10 16h7"/>',
    "arrow": '<path d="M4 12h15M13 6l6 6-6 6"/>',
    "spark": '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
    "money": '<circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5c0-1 1-1.7 2.5-1.7s2.5.7 2.5 1.7-1 1.6-2.5 1.9-2.5.9-2.5 1.9 1 1.7 2.5 1.7 2.5-.7 2.5-1.7"/>',
    "warn": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
    "grid": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
}


def data_uri(path):
    mime, _ = mimetypes.guess_type(path)
    if path.lower().endswith(".svg"):
        mime = "image/svg+xml"
    mime = mime or "application/octet-stream"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def clamp(pt, lo=0.58, hi=1.18):
    px = pt * PX_AT_1600
    return (f"clamp({round(px * lo)}px, {round(pt * PT_TO_VW, 3)}vw, "
            f"{round(px * hi)}px)")


def build_tokens(brand):
    p = brand["palette"]
    t = brand["typography"]
    lay = brand.get("layout", {})
    sc = t["scale"]

    body_pt = sc.get("body_pt", 16)
    h3_pt = max(body_pt + 3, round(sc.get("h2_pt", 34) * 0.42))
    lead_pt = max(body_pt + 2, round(body_pt * 1.28))
    margin_vw = max(3.5, min(10.0, lay.get("margin_pct", 6.2)))
    radius = lay.get("radius_px", 0)

    fh = t["heading"]
    fb = t["body"]
    stack = "system-ui, -apple-system, 'Segoe UI', sans-serif"

    tokens = {
        "--bg": p["background"], "--surface": p["surface"], "--text": p["text"],
        "--muted": p["muted"], "--line": p["line"],
        "--accent": p["accent"], "--accent-soft": p["accent_soft"],
        "--accent-2": p.get("accent_2") or p["accent"],
        "--font-head": f"'{fh}', {stack}",
        "--font-body": f"'{fb}', {stack}",
        "--fs-cover": clamp(sc.get("cover_pt", 54)),
        "--fs-h2": clamp(sc.get("h2_pt", 34)),
        "--fs-h3": clamp(h3_pt, 0.7, 1.1),
        "--fs-stat": clamp(sc.get("stat_pt", sc.get("cover_pt", 54))),
        "--fs-lead": clamp(lead_pt, 0.75, 1.1),
        "--fs-body": clamp(body_pt, 0.8, 1.1),
        "--fs-small-body": clamp(max(11, body_pt - 1), 0.8, 1.1),
        "--fs-small": clamp(sc.get("small_pt", 12), 0.8, 1.1),
        "--margin": f"{round(margin_vw, 2)}vw",
        "--content-max": "1180px",
        "--radius": f"{radius}px",
        "--logo-h": "clamp(26px, 2.4vw, 44px)",
        "--gap-1": "clamp(6px,.55vw,10px)",
        "--gap-2": "clamp(12px,1.1vw,20px)",
        "--gap-3": "clamp(18px,1.7vw,30px)",
        "--gap-4": "clamp(26px,2.6vw,46px)",
        "--pad-card": "clamp(16px,1.5vw,26px)",
    }
    return tokens


WEIGHT_HINTS = [
    ("thin", 100), ("extralight", 200), ("ultralight", 200), ("light", 300),
    ("regular", 400), ("book", 400), ("medium", 500), ("semibold", 600),
    ("demibold", 600), ("extrabold", 800), ("ultrabold", 800), ("black", 900),
    ("heavy", 900), ("bold", 700),
]
FONT_FMT = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def guess_weight(filename):
    low = slug(os.path.splitext(os.path.basename(filename))[0])
    if "variable" in low or "vf" == low[-2:]:
        return "100 900"
    for hint, w in WEIGHT_HINTS:
        if hint in low:
            return str(w)
    return "400"


def to_woff2(path):
    """Пережимает ttf/otf в woff2 — файл дека уменьшается примерно втрое.

    Если brotli не установлен, возвращает None и шрифт встраивается как есть:
    лучше тяжёлый дек с правильной типографикой, чем лёгкий с системной.
    """
    try:
        import io
        from fontTools.ttLib import TTFont
        f = TTFont(path)
        f.flavor = "woff2"
        buf = io.BytesIO()
        f.save(buf)
        return buf.getvalue()
    except Exception:
        return None


def coverage(path, chars):
    """Какие из нужных символов гарнитура реально умеет рисовать."""
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(path, fontNumber=0, lazy=True)
        cps = set()
        for t in f["cmap"].tables:
            cps |= set(t.cmap.keys())
        return {c for c in chars if ord(c) not in cps}
    except Exception:
        return set()


def font_block(brand, kit_dir, warn, used_chars=None):
    """Шрифты бренда: локальные файлы > системный запасной набор.

    Дек почти всегда открывают на чужом ноутбуке или с флешки в зале. Если
    гарнитуру не встроить, браузер подставит системную, и вся выверенная
    типографика поедет — поэтому отсутствие файлов это предупреждение, а не мелочь.
    """
    t = brand["typography"]
    families = [f for f in dict.fromkeys([t.get("heading"), t.get("body")]) if f]
    fonts_dir = os.path.join(kit_dir, "fonts") if kit_dir else None
    css, embedded, total = [], set(), 0

    if fonts_dir and os.path.isdir(fonts_dir):
        files = sorted(os.listdir(fonts_dir))
        for fam in families:
            fs = slug(fam)
            matched = [fn for fn in files
                       if slug(os.path.splitext(fn)[0]).startswith(fs)
                       and os.path.splitext(fn)[1].lower() in FONT_FMT]
            if not matched:
                continue
            # Больше четырёх начертаний в деке не нужно, а вес файла растёт линейно
            keep, seen = [], set()
            for fn in matched:
                w = guess_weight(fn)
                if w in seen or "italic" in slug(fn):
                    continue
                seen.add(w)
                keep.append((fn, w))
            keep.sort(key=lambda kv: (kv[1] != "400", kv[1]))
            for fn, w in keep[:4]:
                path = os.path.join(fonts_dir, fn)
                ext = os.path.splitext(fn)[1].lower()
                data = None
                if ext in (".ttf", ".otf"):
                    data = to_woff2(path)
                if data:
                    uri = "data:font/woff2;base64," + base64.b64encode(data).decode()
                    fmt = "woff2"
                    total += len(data)
                else:
                    uri = data_uri(path)
                    fmt = FONT_FMT[ext]
                    total += os.path.getsize(path)
                css.append(f"@font-face{{font-family:'{fam}';src:url({uri}) "
                           f"format('{fmt}');font-weight:{w};font-style:normal;"
                           f"font-display:swap;}}")
            embedded.add(fam)

            # Молчаливая подмена гарнитуры — самая обидная ошибка в деке:
            # браузер просто берёт следующий шрифт из стека, и заголовки на
            # кириллице оказываются набраны не тем, чем задумано. Латинские
            # дисплейные гарнитуры кириллицу поддерживают далеко не всегда.
            if used_chars and keep:
                # Проверяем каждое начертание: кириллица бывает в regular и
                # отсутствует в bold — заголовки поедут, а обычный текст нет.
                miss = set()
                for fn, _w in keep:
                    miss |= coverage(os.path.join(fonts_dir, fn), used_chars)
                if miss:
                    sample = "".join(sorted(miss)[:12])
                    warn.append(
                        f"Гарнитура «{fam}» не содержит {len(miss)} символов из текста "
                        f"дека (например: {sample}). Браузер подставит другой шрифт, и "
                        f"эти надписи будут набраны не тем, чем задумано. Возьмите "
                        f"версию гарнитуры с нужным алфавитом или другой шрифт.")

    missing = [f for f in families if f not in embedded]
    if missing:
        warn.append(
            "Шрифты не встроены: " + ", ".join(missing) +
            ". На другом компьютере дек откроется системной гарнитурой и будет "
            "выглядеть иначе. Положите файлы в brand-kit/fonts/ или запустите "
            "scripts/get_fonts.py, если гарнитура есть в Google Fonts.")
    elif total:
        print(f"  шрифты встроены: {', '.join(sorted(embedded))} ({total // 1024} КБ)")
    return "\n".join(css)


def embed_assets(html, base_dirs, warn):
    """src="..." → data:URI. Ссылка на файл, которого нет, ломает дек молча,
    поэтому каждый непойманный путь попадает в предупреждения."""
    def repl(m):
        attr, path = m.group(1), m.group(2)
        if path.startswith(("data:", "http:", "https:", "#")):
            return m.group(0)
        for d in base_dirs:
            full = os.path.normpath(os.path.join(d, path))
            if os.path.isfile(full):
                return f'{attr}="{data_uri(full)}"'
        warn.append(f"Файл не найден и не встроен: {path}")
        return m.group(0)
    return re.sub(r'\b(src|href)="([^"]+\.(?:png|jpg|jpeg|svg|gif|webp))"', repl, html)


def inline_icons(html, warn):
    def repl(m):
        name = m.group(1)
        if name not in ICONS:
            warn.append(f"Нет иконки '{name}'. Доступны: {', '.join(sorted(ICONS))}")
            return ""
        return ('<span class="ic"><svg viewBox="0 0 24 24" fill="none" '
                'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
                'stroke-linejoin="round">' + ICONS[name] + "</svg></span>")
    return re.sub(r'<i\s+data-icon="([a-z0-9_-]+)"\s*/?>(?:</i>)?', repl, html)


def main():
    ap = argparse.ArgumentParser(description="Фрагмент слайдов + brand.json → один HTML")
    ap.add_argument("slides", help="HTML-фрагмент: только <section class=\"slide\">…")
    ap.add_argument("--brand", required=True, help="brand-kit/brand.json")
    ap.add_argument("--out", default="deck.html")
    ap.add_argument("--title", help="заголовок вкладки браузера")
    ap.add_argument("--tag", help="подпись в правом нижнем углу (например, сайт)")
    a = ap.parse_args()

    with open(a.brand, encoding="utf-8") as f:
        brand = json.load(f)
    with open(a.slides, encoding="utf-8") as f:
        slides = f.read()

    if "<section" not in slides:
        sys.exit("В файле слайдов нет ни одного <section class=\"slide\">.")

    kit_dir = os.path.dirname(os.path.abspath(a.brand))
    warn = []
    slides = inline_icons(slides, warn)
    # Пути к картинкам ищем и от папки с brand.json, и от её родителя: в
    # упакованном ките brand.json лежит внутри assets/, и путь "assets/media/x.png"
    # без родителя превратился бы в assets/assets/media/x.png.
    slides = embed_assets(slides, [kit_dir, os.path.join(kit_dir, "assets"),
                                   os.path.dirname(kit_dir),
                                   os.path.dirname(os.path.abspath(a.slides))], warn)

    tokens = build_tokens(brand)
    root = ":root{" + "".join(f"{k}:{v};" for k, v in tokens.items()) + "}"
    css = open(os.path.join(ASSETS, "deck.css"), encoding="utf-8").read()
    js = open(os.path.join(ASSETS, "deck.js"), encoding="utf-8").read()
    body_text = re.sub(r"<[^>]+>", " ", slides)
    body_text = re.sub(r"&[a-z]+;|&#\d+;", " ", body_text)
    used_chars = {c for c in body_text if c.isalnum() or c in "%№₸$€—–"}
    fonts = font_block(brand, kit_dir, warn, used_chars)

    title = a.title or brand.get("name", "Presentation")
    tag = a.tag or brand.get("tag") or ""
    n = slides.count('<section')

    html = f"""<!DOCTYPE html><html lang="{brand.get('tone', {}).get('language', 'ru')}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{fonts}
{root}
{css}</style></head>
<body>
<div class="progress"></div>
<div class="deck">
{slides}
</div>
<div class="counter"></div>
{f'<div class="brandtag">{tag}</div>' if tag else ''}
<div class="dots"></div>
<script>{js}</script>
</body></html>"""

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(html)

    size = os.path.getsize(a.out)
    print(f"Готово: {a.out} — {n} слайдов, {size // 1024} КБ")
    if size > 12 * 1024 * 1024:
        print("  · файл больше 12 МБ: почтовые клиенты такое режут. "
              "Пережмите фотографии перед вставкой.")
    for w in dict.fromkeys(warn):
        print(f"  ! {w}")


if __name__ == "__main__":
    main()
