#!/usr/bin/env python3
"""Разбор стиля из презентаций клиента: PPTX → brand.json + ассеты + отчёт.

    python3 extract_style.py deck1.pptx deck2.pptx --out brand-kit

Читает две вещи и не путает их между собой:
  * что объявлено в теме файла (палитра и шрифты мастера) — это намерение дизайнера;
  * что реально стоит на слайдах (частоты цветов, кеглей, начертаний) — это практика.
Расхождение между ними — нормальная ситуация, и она попадает в отчёт, а не
замазывается: тема может быть дефолтной от шаблона, пока весь дек размечен руками.

Ничего не выдумывает. Чего в файлах нет, помечается в отчёте как пробел.
"""

import argparse
import collections
import colorsys
import json
import os
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
EMU_PER_PT = 12700
EMU_PER_IN = 914400

# Гарнитуры, которые Office подставляет по умолчанию: если дек размечен только
# ими, это не «фирменный шрифт», а отсутствие решения — так и пишем в отчёт.
DEFAULT_FONTS = {"calibri", "calibri light", "arial", "times new roman", "aptos",
                 "aptos display", "+mn-lt", "+mj-lt"}


# ------------------------------------------------------------------ цвет

def hex_norm(v):
    v = (v or "").strip().lstrip("#").upper()
    return v if re.fullmatch(r"[0-9A-F]{6}", v) else None


def luminance(hexv):
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def hsl(hexv):
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return round(h * 360), round(s * 100), round(l * 100)


def spread(hexv):
    """Разброс RGB-каналов — честная мера «цветности».

    Насыщенность в HLS у очень светлых и очень тёмных тонов раздувается:
    почти белый #ECF1F7 показывает 41%, хотя это нейтральный текст. Разброс
    каналов такой ошибки не делает, поэтому нейтральность считаем по нему.
    """
    ch = [int(hexv[i:i + 2], 16) for i in (0, 2, 4)]
    return max(ch) - min(ch)


def is_greyish(hexv, max_spread=40):
    return spread(hexv) <= max_spread


def shift_lightness(hexv, delta):
    # rgb_to_hls отдаёт (h, l, s) — порядок неочевидный, перепутать легко.
    h, l, s = colorsys.rgb_to_hls(*(int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4)))
    l = max(0.0, min(1.0, l + delta))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in (r, g, b)))


# ------------------------------------------------------------------ тема

def read_theme(z, name):
    """Палитра и шрифты, объявленные в теме файла."""
    try:
        root = ET.fromstring(z.read(name))
    except (KeyError, ET.ParseError):
        return {}, {}
    colors = {}
    scheme = root.find(".//a:clrScheme", NS)
    if scheme is not None:
        for child in scheme:
            slot = child.tag.split("}")[1]
            srgb = child.find("a:srgbClr", NS)
            sysc = child.find("a:sysClr", NS)
            val = None
            if srgb is not None:
                val = hex_norm(srgb.get("val"))
            elif sysc is not None:
                val = hex_norm(sysc.get("lastClr"))
            if val:
                colors[slot] = val
    fonts = {}
    fs = root.find(".//a:fontScheme", NS)
    if fs is not None:
        for key, tag in (("major", "a:majorFont"), ("minor", "a:minorFont")):
            node = fs.find(tag, NS)
            if node is not None:
                latin = node.find("a:latin", NS)
                if latin is not None and latin.get("typeface"):
                    fonts[key] = latin.get("typeface")
    return colors, fonts


def resolve_scheme(val, theme):
    """schemeClr val -> hex. Office держит два имени для одного слота."""
    alias = {"tx1": "dk1", "bg1": "lt1", "tx2": "dk2", "bg2": "lt2"}
    return theme.get(alias.get(val, val))


# ------------------------------------------------------------------ слайды

def iter_slide_parts(z):
    names = [n for n in z.namelist()
             if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
    return sorted(names, key=lambda n: int(re.search(r"(\d+)", os.path.basename(n)).group(1)))


def collect_from_slides(z, theme_colors, slide_wh):
    """Частоты цветов, шрифтов и кеглей + геометрия текстовых блоков."""
    colors = collections.Counter()
    text_colors = collections.Counter()
    fonts = collections.Counter()
    sizes = collections.Counter()
    size_by_font = collections.defaultdict(collections.Counter)
    size_slides = collections.defaultdict(set)
    first_slide_sizes = set()
    bold_sizes = collections.Counter()
    corner_adj = collections.Counter()
    lefts, tops, widths = collections.Counter(), collections.Counter(), collections.Counter()
    texts = []
    titles = []
    per_slide_blocks = []
    bg_hits = collections.Counter()

    for slide_ix, name in enumerate(iter_slide_parts(z)):
        try:
            root = ET.fromstring(z.read(name))
        except ET.ParseError:
            continue

        bg = root.find(".//p:bg", NS)
        if bg is not None:
            for tag, attr in (("a:srgbClr", "val"), ("a:schemeClr", "val")):
                for node in bg.iter("{%s}%s" % (NS["a"], tag.split(":")[1])):
                    v = (hex_norm(node.get(attr)) if tag.endswith("srgbClr")
                         else resolve_scheme(node.get(attr), theme_colors))
                    if v:
                        bg_hits[v] += 1
                        break

        blocks = 0
        slide_text = []
        sw, sh = slide_wh
        for sp in root.iter("{%s}sp" % NS["p"]):
            xfrm = sp.find(".//a:xfrm", NS)
            # Дизайнеры обычно кладут фон полноэкранным прямоугольником, а не в <p:bg>.
            # Такую фигуру нельзя считать ни контентом (испортит поля), ни просто
            # цветом на слайде (задавит палитру частотой) — это фон.
            full_bleed = False
            if xfrm is not None:
                off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
                x = int(off.get("x", 0)) if off is not None else 0
                y = int(off.get("y", 0)) if off is not None else 0
                cx = int(ext.get("cx", 0)) if ext is not None else 0
                cy = int(ext.get("cy", 0)) if ext is not None else 0
                full_bleed = (abs(x) <= sw * 0.01 and abs(y) <= sh * 0.01
                              and cx >= sw * 0.97 and cy >= sh * 0.97)
                if full_bleed:
                    fill = sp.find(".//a:solidFill", NS)
                    if fill is not None:
                        srgb = fill.find("a:srgbClr", NS)
                        sch = fill.find("a:schemeClr", NS)
                        v = hex_norm(srgb.get("val")) if srgb is not None else (
                            resolve_scheme(sch.get("val"), theme_colors) if sch is not None else None)
                        if v:
                            bg_hits[v] += 1
                    continue
                if off is not None:
                    lefts[x] += 1
                    tops[y] += 1
                if ext is not None:
                    widths[cx] += 1
            geom = sp.find(".//a:prstGeom", NS)
            if geom is not None and geom.get("prst") == "roundRect":
                gd = geom.find(".//a:gd", NS)
                if gd is not None and gd.get("fmla", "").startswith("val "):
                    corner_adj[int(gd.get("fmla").split()[1])] += 1

            # заливки фигуры
            for fill in sp.findall(".//a:solidFill", NS):
                srgb = fill.find("a:srgbClr", NS)
                sch = fill.find("a:schemeClr", NS)
                v = hex_norm(srgb.get("val")) if srgb is not None else (
                    resolve_scheme(sch.get("val"), theme_colors) if sch is not None else None)
                if v:
                    colors[v] += 1

            tx = sp.find(".//p:txBody", NS)
            if tx is None:
                continue
            blocks += 1
            for para in tx.findall("a:p", NS):
                buf = []
                for run in para.findall("a:r", NS):
                    t = run.find("a:t", NS)
                    if t is not None and t.text:
                        buf.append(t.text)
                    rpr = run.find("a:rPr", NS)
                    if rpr is None:
                        continue
                    latin = rpr.find("a:latin", NS)
                    face = latin.get("typeface") if latin is not None else None
                    if face:
                        fonts[face] += 1
                    sz = rpr.get("sz")
                    if sz:
                        pt = round(int(sz) / 100)
                        sizes[pt] += 1
                        size_slides[pt].add(slide_ix)
                        if slide_ix == 0:
                            first_slide_sizes.add(pt)
                        if face:
                            size_by_font[face][pt] += 1
                        if rpr.get("b") == "1":
                            bold_sizes[pt] += 1
                    fill = rpr.find("a:solidFill", NS)
                    if fill is not None:
                        srgb = fill.find("a:srgbClr", NS)
                        sch = fill.find("a:schemeClr", NS)
                        v = hex_norm(srgb.get("val")) if srgb is not None else (
                            resolve_scheme(sch.get("val"), theme_colors) if sch is not None else None)
                        if v:
                            text_colors[v] += 1
                line = "".join(buf).strip()
                if line:
                    slide_text.append(line)
        if slide_text:
            titles.append(slide_text[0])
            texts.extend(slide_text)
        per_slide_blocks.append(blocks)

    return {
        "colors": colors, "text_colors": text_colors, "fonts": fonts, "sizes": sizes,
        "size_by_font": size_by_font, "bold_sizes": bold_sizes, "corner_adj": corner_adj,
        "size_slides": size_slides, "first_slide_sizes": first_slide_sizes,
        "lefts": lefts, "tops": tops, "widths": widths,
        "texts": texts, "titles": titles, "blocks": per_slide_blocks, "bg": bg_hits,
    }


# ------------------------------------------------------------------ медиа

def extract_media(z, outdir, notes):
    media = [n for n in z.namelist() if n.startswith("ppt/media/")]
    os.makedirs(outdir, exist_ok=True)
    saved = []
    for n in media:
        ext = os.path.splitext(n)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".emf", ".wmf"):
            continue
        data = z.read(n)
        base = os.path.basename(n)
        path = os.path.join(outdir, base)
        i = 1
        while os.path.exists(path):
            stem, e = os.path.splitext(base)
            path = os.path.join(outdir, f"{stem}_{i}{e}")
            i += 1
        with open(path, "wb") as f:
            f.write(data)
        item = {"file": os.path.relpath(path, os.path.dirname(outdir)),
                "bytes": len(data), "format": ext.lstrip(".")}
        try:
            from PIL import Image
            with Image.open(path) as im:
                item["width"], item["height"] = im.size
                item["alpha"] = im.mode in ("RGBA", "LA") or "transparency" in im.info
        except Exception:
            pass
        saved.append(item)

    # Кандидаты в логотипы: мелкие, с прозрачностью или векторные.
    for m in saved:
        w, h = m.get("width", 0), m.get("height", 0)
        vector = m["format"] in ("svg", "emf", "wmf")
        small = 0 < max(w, h) <= 900
        wide = h and 0.15 <= (w / h if h else 0) <= 8
        m["likely_logo"] = bool(vector or (small and m.get("alpha") and wide))
    if not any(m["likely_logo"] for m in saved):
        notes.append("Логотип не опознан автоматически — попросите файл логотипа отдельно "
                     "или укажите нужный файл из assets/media вручную.")
    return saved


# ------------------------------------------------------------------ сборка

def build_palette(stats, theme_colors, notes):
    """Собирает токены. Практика со слайдов важнее объявленной темы."""
    used = stats["colors"] + stats["text_colors"]

    bg = None
    if stats["bg"]:
        bg = stats["bg"].most_common(1)[0][0]
    if not bg:
        # фон не размечен явно — берём lt1/dk1 из темы
        bg = theme_colors.get("lt1") or "FFFFFF"
        notes.append("Фон слайдов не задан явно в файлах — взят из темы. Проверьте: "
                     "если деки тёмные, а здесь светлый фон, укажите фон вручную.")
    dark = luminance(bg) < 0.4

    # текст: самый частый цвет текста с достаточным контрастом к фону
    # Основной текст — не самый частый цвет, а самый контрастный из нейтральных:
    # приглушённая подпись обычно встречается чаще заголовка, и если брать по
    # частоте, весь дек уезжает в серый.
    tc = stats["text_colors"]
    top_freq = max(tc.values()) if tc else 0
    cands = [(contrast(h, bg), h) for h, n in tc.items()
             if n >= max(1, top_freq * 0.15) and is_greyish(h) and contrast(h, bg) >= 4.5]
    text = max(cands)[1] if cands else None
    if not text:
        text = theme_colors.get("dk1") if not dark else theme_colors.get("lt1")
    if not text or contrast(text, bg) < 3.0:
        text = "F5F5F5" if dark else "16181D"
        notes.append("Основной цвет текста не удалось определить по слайдам — взят "
                     "нейтральный. Задайте его вручную, если в бренде он другой.")

    # акцент: самый частый насыщенный цвет, не совпадающий с фоном и текстом
    # Не просто «самый частый цветной»: приглушённый серо-синий текста обычно
    # встречается чаще акцента. Вес по насыщенности вытаскивает именно акцент.
    accent = None
    ranked = []
    for hexv, n in used.most_common(40):
        if hexv in (bg, text) or contrast(hexv, bg) < 1.6:
            continue
        if is_greyish(hexv):
            continue
        _, sat, lig = hsl(hexv)
        if lig < 6 or lig > 96:
            continue
        ranked.append((n * (spread(hexv) / 255.0) ** 1.2, hexv))
    if ranked:
        ranked.sort(reverse=True)
        accent = ranked[0][1]
    accent_source = "по частоте и насыщенности на слайдах"
    if not accent:
        for slot in ("accent1", "accent2", "accent3"):
            v = theme_colors.get(slot)
            if v and not is_greyish(v):
                accent, accent_source = v, f"из темы ({slot})"
                break
    if not accent:
        accent, accent_source = ("C9A227" if dark else "1B4DFF"), "не найден, подставлен нейтральный"
        notes.append("Акцентный цвет не найден ни на слайдах, ни в теме — подставлен "
                     "нейтральный. Это первое, что стоит поправить руками.")

    # вторичный акцент: следующий насыщенный другого тона
    accent2 = None
    for _, hexv in sorted(ranked, reverse=True):
        if hexv == accent:
            continue
        if abs(hsl(hexv)[0] - hsl(accent)[0]) > 25:
            accent2 = hexv
            break
    accent_soft = shift_lightness(accent, 0.12 if dark else -0.10)

    surface = None
    for hexv, _ in stats["colors"].most_common(20):
        if hexv == bg or not is_greyish(hexv, 45):
            continue
        d = luminance(hexv) - luminance(bg)
        if 0.008 < abs(d) < 0.18 and ((d > 0) == dark):
            surface = hexv
            break
    if not surface:
        surface = shift_lightness(bg, 0.06 if dark else -0.035)

    # Приглушённый — тоже наблюдаемый цвет, если такой есть: производный от
    # основного оттенок почти всегда выглядит чужеродно рядом с настоящим.
    muted = None
    mc = [(n, h) for h, n in tc.items()
          if h != text and is_greyish(h, 55) and 2.5 <= contrast(h, bg) < contrast(text, bg)]
    if mc:
        muted = max(mc)[1]
    else:
        muted = shift_lightness(text, -0.22 if not dark else -0.28)
    line = shift_lightness(bg, 0.14 if dark else -0.10)

    pal = {
        "background": "#" + bg, "surface": "#" + surface, "text": "#" + text,
        "muted": "#" + muted, "line": "#" + line,
        "accent": "#" + accent, "accent_soft": "#" + accent_soft,
        "accent_2": ("#" + accent2) if accent2 else None,
        "mode": "dark" if dark else "light",
        "_accent_source": accent_source,
    }
    c = contrast(text, bg)
    if c < 4.5:
        notes.append(f"Контраст текста к фону {c}:1 — ниже 4.5:1. На проекторе это "
                     "читается плохо; стоит взять более контрастный оттенок текста.")
    ca = contrast(accent, bg)
    if ca < 3.0:
        notes.append(f"Контраст акцента к фону {ca}:1. Акцентом можно красить крупные "
                     "заголовки и плашки, но не мелкий текст.")
    return pal


def build_type(stats, theme_fonts, notes):
    used = stats["fonts"]
    ranked = [f for f, _ in used.most_common() if f and not f.startswith("+")]
    branded = [f for f in ranked if f.lower() not in DEFAULT_FONTS]

    heading = body = None
    if branded:
        heading = branded[0]
        body = branded[1] if len(branded) > 1 else branded[0]
    if not heading:
        heading = theme_fonts.get("major")
        body = theme_fonts.get("minor") or heading
        if heading:
            notes.append("На слайдах фирменных шрифтов нет — взяты из темы мастера.")
    if not heading:
        heading = body = "Inter"
        notes.append("Шрифты определить не удалось — подставлен нейтральный Inter. "
                     "Назовите нужную гарнитуру, и я пересоберу.")
    elif heading.lower() in DEFAULT_FONTS and body and body.lower() in DEFAULT_FONTS:
        notes.append(f"В презентациях используются только офисные шрифты по умолчанию "
                     f"({heading}). Это не фирменная гарнитура, а её отсутствие — "
                     "имеет смысл выбрать шрифт осознанно.")

    # различить заголовочную и текстовую гарнитуру по кеглям
    if body and heading and body != heading:
        hs = stats["size_by_font"].get(heading)
        bs = stats["size_by_font"].get(body)
        if hs and bs:
            avg = lambda c: sum(k * v for k, v in c.items()) / max(1, sum(c.values()))
            if avg(bs) > avg(hs):
                heading, body = body, heading

    all_sizes = stats["sizes"]
    if all_sizes:
        # Основной кегль — медиана по массе в диапазоне текста, а не мода:
        # мода скачет между 13 и 15 от одной подписи.
        body_pool = sorted(pt for pt, n in all_sizes.items() if 10 <= pt <= 22 for _ in range(n))
        body_pt = body_pool[len(body_pool) // 2] if body_pool else 16

        display = [pt for pt in all_sizes if pt >= max(24, body_pt * 1.6)]
        by_slides = stats.get("size_slides", {})
        first = stats.get("first_slide_sizes") or set()

        # Обложка — самый крупный кегль первого слайда: он и есть титул дека.
        # Брать максимум по всему деку нельзя, там обычно крупная цифра статистики.
        cover_pt = max((pt for pt in first if pt >= body_pt * 1.6), default=None) \
            or (max(display) if display else round(body_pt * 3.4))
        # Заголовок слайда — кегль, который встречается на наибольшем числе слайдов.
        h2_candidates = [pt for pt in display if pt != cover_pt]
        h2_pt = max(h2_candidates, key=lambda pt: (len(by_slides.get(pt, ())), pt)) \
            if h2_candidates else round(cover_pt * 0.68)
        stat_pool = [pt for pt in display if pt not in first]
        stat_pt = max(stat_pool) if stat_pool else cover_pt
        small_pt = min((pt for pt, n in all_sizes.items() if pt >= 8 and n >= 2),
                       default=max(9, body_pt - 3))
        scale = {"cover_pt": cover_pt, "h2_pt": h2_pt, "stat_pt": stat_pt,
                 "body_pt": body_pt, "small_pt": small_pt}
    else:
        scale = {"cover_pt": 54, "h2_pt": 34, "stat_pt": 60, "body_pt": 16, "small_pt": 12}
        notes.append("Кегли в файлах не размечены явно — типографическая шкала взята "
                     "по умолчанию и почти наверняка требует правки.")

    return {"heading": heading, "body": body, "scale": scale,
            "heading_is_default": heading.lower() in DEFAULT_FONTS}


def build_layout(stats, slide_wh, notes):
    w_emu, h_emu = slide_wh
    ratio = round(w_emu / h_emu, 4) if h_emu else 1.7778
    lefts = [x for x, n in stats["lefts"].most_common(6) if n >= 2]
    margin_emu = min(lefts) if lefts else int(w_emu * 0.062)
    margin_pct = round(100 * margin_emu / w_emu, 2) if w_emu else 6.2

    radius = 0
    if stats["corner_adj"]:
        adj = stats["corner_adj"].most_common(1)[0][0]
        radius = round(adj / 100000 * 40)

    blocks = stats["blocks"]
    avg_blocks = round(sum(blocks) / len(blocks), 1) if blocks else 0
    density = "плотные" if avg_blocks >= 7 else ("средние" if avg_blocks >= 4 else "воздушные")

    if abs(ratio - 1.7778) > 0.02 and abs(ratio - 1.3333) > 0.02:
        notes.append(f"Нестандартное соотношение сторон {ratio}. Дек будет собран в 16:9 — "
                     "скажите, если нужно сохранить исходное.")
    return {"aspect": "16:9" if ratio > 1.5 else "4:3", "ratio": ratio,
            "margin_pct": margin_pct, "radius_px": radius,
            "avg_text_blocks_per_slide": avg_blocks, "density": density}


def analyse_text(stats):
    texts = stats["texts"]
    titles = stats["titles"][:40]
    joined = " ".join(texts)
    words = re.findall(r"[A-Za-zА-Яа-яЁё]+", joined)
    caps_titles = sum(1 for t in titles if t.isupper() and len(t) > 3)
    lang = "ru" if len(re.findall(r"[А-Яа-яЁё]", joined)) > len(re.findall(r"[A-Za-z]", joined)) else "en"
    return {
        "language": lang,
        "slide_count_sampled": len(stats["blocks"]),
        "avg_title_words": round(sum(len(t.split()) for t in titles) / max(1, len(titles)), 1),
        "uppercase_titles": caps_titles,
        "uppercase_title_share": round(caps_titles / max(1, len(titles)), 2),
        "avg_words_per_slide": round(len(words) / max(1, len(stats["blocks"])), 1),
        "sample_titles": titles[:12],
    }


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description="PPTX → brand.json + ассеты + отчёт")
    ap.add_argument("pptx", nargs="+")
    ap.add_argument("--out", default="brand-kit")
    ap.add_argument("--name", help="название бренда (по умолчанию — из имени файла)")
    a = ap.parse_args()

    notes = []
    merged = {
        "colors": collections.Counter(), "text_colors": collections.Counter(),
        "fonts": collections.Counter(), "sizes": collections.Counter(),
        "size_by_font": collections.defaultdict(collections.Counter),
        "bold_sizes": collections.Counter(), "corner_adj": collections.Counter(),
        "lefts": collections.Counter(), "tops": collections.Counter(),
        "widths": collections.Counter(), "bg": collections.Counter(),
        "size_slides": collections.defaultdict(set), "first_slide_sizes": set(),
        "texts": [], "titles": [], "blocks": [],
    }
    theme_colors, theme_fonts = {}, {}
    slide_wh = (12192000, 6858000)
    media = []
    sources = []

    os.makedirs(a.out, exist_ok=True)
    media_dir = os.path.join(a.out, "assets", "media")

    for path in a.pptx:
        if not os.path.exists(path):
            sys.exit(f"Файл не найден: {path}")
        try:
            z = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            sys.exit(f"Не похоже на PPTX: {path}")
        with z:
            for tname in sorted(n for n in z.namelist()
                                if re.fullmatch(r"ppt/theme/theme\d+\.xml", n)):
                tc, tf = read_theme(z, tname)
                for k, v in tc.items():
                    theme_colors.setdefault(k, v)
                for k, v in tf.items():
                    theme_fonts.setdefault(k, v)
                break
            try:
                pres = ET.fromstring(z.read("ppt/presentation.xml"))
                sz = pres.find("p:sldSz", NS)
                if sz is not None:
                    slide_wh = (int(sz.get("cx")), int(sz.get("cy")))
            except (KeyError, ET.ParseError):
                pass

            st = collect_from_slides(z, theme_colors, slide_wh)
            for key in ("colors", "text_colors", "fonts", "sizes", "bold_sizes",
                        "corner_adj", "lefts", "tops", "widths", "bg"):
                merged[key] += st[key]
            for f, c in st["size_by_font"].items():
                merged["size_by_font"][f] += c
            for pt, sl in st["size_slides"].items():
                merged["size_slides"][pt] |= sl
            merged["first_slide_sizes"] |= st["first_slide_sizes"]
            merged["texts"] += st["texts"]
            merged["titles"] += st["titles"]
            merged["blocks"] += st["blocks"]
            media += extract_media(z, media_dir, notes)
            sources.append({"file": os.path.basename(path), "slides": len(st["blocks"])})

    if not merged["blocks"]:
        sys.exit("В презентациях не нашлось слайдов с текстом — разбирать нечего.")

    palette = build_palette(merged, theme_colors, notes)
    typo = build_type(merged, theme_fonts, notes)
    layout = build_layout(merged, slide_wh, notes)
    tone = analyse_text(merged)

    total_slides = sum(s["slides"] for s in sources)
    if total_slides < 12:
        notes.append(f"Разобрано всего {total_slides} слайдов — выводы о стиле шаткие. "
                     "Две-три полные презентации дают заметно более надёжный результат.")

    brand = {
        "name": a.name or os.path.splitext(os.path.basename(a.pptx[0]))[0],
        "sources": sources,
        "palette": palette,
        "typography": typo,
        "layout": layout,
        "tone": tone,
        "media": media,
        "theme_declared": {"colors": theme_colors, "fonts": theme_fonts},
        "observed": {
            "top_colors": merged["colors"].most_common(12),
            "top_text_colors": merged["text_colors"].most_common(8),
            "top_fonts": merged["fonts"].most_common(8),
            "top_sizes": merged["sizes"].most_common(10),
        },
        "notes": notes,
    }

    with open(os.path.join(a.out, "brand.json"), "w", encoding="utf-8") as f:
        json.dump(brand, f, ensure_ascii=False, indent=2)

    logos = [m for m in media if m["likely_logo"]]
    lines = [
        f"# Разбор стиля: {brand['name']}", "",
        "Собрано автоматически из презентаций. Проверьте помеченные места — "
        "скрипт читает файлы, но не знает вашего бренда.", "",
        "## Источники", "",
    ]
    for s in sources:
        lines.append(f"- {s['file']} — {s['slides']} слайдов")
    lines += [
        "", "## Палитра", "",
        f"- Режим: **{palette['mode']}**",
        f"- Фон `{palette['background']}` · Поверхность `{palette['surface']}`",
        f"- Текст `{palette['text']}` · контраст к фону "
        f"{contrast(palette['text'].lstrip('#'), palette['background'].lstrip('#'))}:1",
        f"- Акцент `{palette['accent']}` ({palette['_accent_source']})",
    ]
    if palette["accent_2"]:
        lines.append(f"- Второй акцент `{palette['accent_2']}`")
    lines += [
        "", "## Типографика", "",
        f"- Заголовки: **{typo['heading']}**",
        f"- Текст: **{typo['body']}**",
        f"- Шкала: обложка {typo['scale']['cover_pt']}pt · заголовок {typo['scale']['h2_pt']}pt · "
        f"крупная цифра {typo['scale'].get('stat_pt', '—')}pt · "
        f"текст {typo['scale']['body_pt']}pt · мелкое {typo['scale']['small_pt']}pt",
        "", "## Сетка и плотность", "",
        f"- Формат {layout['aspect']} · поля {layout['margin_pct']}% ширины · "
        f"скругление {layout['radius_px']}px",
        f"- В среднем {layout['avg_text_blocks_per_slide']} текстовых блоков на слайд "
        f"({layout['density']} слайды)",
        "", "## Как написаны слайды", "",
        f"- Язык: {tone['language']} · слов на слайд: {tone['avg_words_per_slide']}",
        f"- Заголовки: {tone['avg_title_words']} слов в среднем, "
        f"КАПСОМ — {int(tone['uppercase_title_share'] * 100)}%",
        "", "Примеры заголовков из ваших дек:", "",
    ]
    for t in tone["sample_titles"][:8]:
        lines.append(f"- {t}")
    lines += ["", "## Ассеты", "",
              f"- Извлечено изображений: {len(media)}, из них похожи на логотипы: {len(logos)}"]
    for m in logos[:8]:
        lines.append(f"  - `{m['file']}` — {m.get('width','?')}×{m.get('height','?')}, {m['format']}")
    if notes:
        lines += ["", "## Что проверить руками", ""]
        for n in notes:
            lines.append(f"- {n}")
    else:
        lines += ["", "## Что проверить руками", "", "- Явных пробелов не обнаружено."]

    with open(os.path.join(a.out, "EXTRACTION.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Готово: {a.out}/brand.json + {a.out}/EXTRACTION.md")
    print(f"  слайдов разобрано: {total_slides} из {len(sources)} файлов")
    print(f"  режим: {palette['mode']} · акцент {palette['accent']} ({palette['_accent_source']})")
    print(f"  шрифты: {typo['heading']} / {typo['body']}")
    print(f"  изображений: {len(media)} (кандидатов в логотипы: {len(logos)})")
    if notes:
        print(f"  требует проверки: {len(notes)} пункт(ов) — см. EXTRACTION.md")


if __name__ == "__main__":
    main()
