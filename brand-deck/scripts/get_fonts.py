#!/usr/bin/env python3
"""Сбор фирменных гарнитур в brand-kit/fonts/.

    python3 get_fonts.py "Space Grotesk" "IBM Plex Sans" --out brand-kit/fonts
    python3 get_fonts.py "Manrope" --out brand-kit/fonts --system

Сначала пробует Google Fonts, при недоступности сети берёт установленную в
системе гарнитуру того же имени. Флаг --system пропускает сеть сразу.

Нужно, чтобы дек выглядел одинаково на любом компьютере: без встроенных
шрифтов браузер подставит системный, и вся типографика поедет. Если гарнитуры
нет в Google Fonts (лицензионный корпоративный шрифт), положите файлы в ту же
папку руками — build_deck.py подхватит по имени файла.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()


def from_system(family, outdir):
    """Копирует уже установленную в системе гарнитуру.

    Нужно чаще, чем кажется: в закрытых контурах и песочницах доступа к
    Google Fonts нет, а нужный шрифт может быть установлен локально —
    отсутствие сети не повод собирать дек системным шрифтом.
    """
    found = []
    try:
        out = subprocess.run(["fc-list", "--format", "%{file}\n", family],
                             capture_output=True, text=True, timeout=20).stdout
        found = [ln.strip() for ln in out.splitlines() if ln.strip()]
    except Exception:
        pass
    if not found:
        slug = re.sub(r"[^a-z0-9]+", "", family.lower())
        for root in ("/usr/share/fonts", "/usr/local/share/fonts",
                     os.path.expanduser("~/.fonts"),
                     os.path.expanduser("~/Library/Fonts"), "C:/Windows/Fonts"):
            for ext in ("ttf", "otf", "woff2"):
                for p in glob.glob(os.path.join(root, "**", f"*.{ext}"), recursive=True):
                    if re.sub(r"[^a-z0-9]+", "", os.path.basename(p).lower()).startswith(slug):
                        found.append(p)
    # Деку нужны обычное и жирное начертания; по алфавиту первыми идут
    # ExtraLight и Black, поэтому сортируем по полезности, а не по имени.
    PREF = ["regular", "book", "medium", "semibold", "demibold", "bold",
            "extrabold", "light", "black", "thin", "extralight"]

    def rank(path):
        low = re.sub(r"[^a-z]+", "", os.path.splitext(os.path.basename(path))[0].lower())
        if "variable" in low:
            return -1
        for i, w in enumerate(PREF):
            if low.endswith(w):
                return i
        return len(PREF)

    keep, seen = [], set()
    for p in sorted(found, key=lambda x: (rank(x), x)):
        low = os.path.basename(p).lower()
        if "italic" in low or "oblique" in low:
            continue
        key = re.sub(r"[^a-z]+", "", os.path.splitext(low)[0])
        if key in seen:
            continue
        seen.add(key)
        keep.append(p)
    copied = []
    for p in keep[:4]:
        dst = os.path.join(outdir, os.path.basename(p))
        shutil.copy(p, dst)
        copied.append(dst)
    return copied


def main():
    ap = argparse.ArgumentParser(description="Гарнитуры бренда → brand-kit/fonts")
    ap.add_argument("family", nargs="+")
    ap.add_argument("--out", default="fonts")
    ap.add_argument("--weights", default="400;600;700")
    ap.add_argument("--system", action="store_true",
                    help="искать только среди установленных в системе шрифтов")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    ok, failed = [], []
    for fam in a.family:
        if a.system:
            got = from_system(fam, a.out)
            if got:
                ok += [(fam, g, os.path.getsize(g)) for g in got]
            else:
                failed.append((fam, "не найдено среди установленных шрифтов"))
            continue
        q = fam.replace(" ", "+")
        url = f"https://fonts.googleapis.com/css2?family={q}:wght@{a.weights}&display=swap"
        try:
            css = fetch(url).decode("utf-8", "replace")
        except Exception as e:
            got = from_system(fam, a.out)
            if got:
                ok += [(fam, g, os.path.getsize(g)) for g in got]
                print(f"  {fam}: Google Fonts недоступен, взял установленную в системе")
                continue
            failed.append((fam, f"не найдено ни в Google Fonts ({e}), ни в системе"))
            continue
        urls = re.findall(r"url\((https://[^)]+\.woff2)\)", css)
        if not urls:
            failed.append((fam, "нет woff2 в ответе"))
            continue
        # Латиница обычно последним блоком; берём самый крупный файл как основной.
        best, best_data = None, b""
        for u in urls[-4:]:
            try:
                d = fetch(u)
            except Exception:
                continue
            if len(d) > len(best_data):
                best, best_data = u, d
        if not best_data:
            failed.append((fam, "не удалось скачать"))
            continue
        name = re.sub(r"[^A-Za-z0-9]+", "", fam) + ".woff2"
        path = os.path.join(a.out, name)
        with open(path, "wb") as f:
            f.write(best_data)
        ok.append((fam, path, len(best_data)))

    for fam, path, n in ok:
        print(f"  {fam} → {path} ({n // 1024} КБ)")
    for fam, why in failed:
        print(f"  ! {fam}: {why}")
    if failed:
        print("\nНедостающие гарнитуры положите в", a.out,
              "вручную (ttf/otf/woff2), имя файла должно начинаться с названия шрифта.")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
