#!/usr/bin/env python3
"""Экспорт дека в 16:9 PDF: скриншот каждого слайда, затем сшивка.

    python3 render_pdf.py deck.html deck.pdf --scale 2

Печать через CSS здесь не годится: дек интерактивный, счётчики анимированы,
градиенты и полупрозрачность браузер при печати упрощает. Скриншоты дают
ровно то, что видит зритель, и замораживают цифры на финальном значении.
"""

import argparse
import glob
import os
import shutil
import sys
import tempfile


def find_chrome(explicit=None):
    if explicit:
        return explicit
    for c in [os.environ.get("CHROME_BIN"), "/opt/pw-browsers/chromium",
              shutil.which("google-chrome"), shutil.which("chromium"),
              shutil.which("chromium-browser"),
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]:
        if c and os.path.exists(c):
            return c
    for root in ("/opt/pw-browsers", os.path.expanduser("~/.cache/ms-playwright")):
        for p in glob.glob(os.path.join(root, "**", "chrome"), recursive=True):
            if os.access(p, os.X_OK):
                return p
    return None


def main():
    ap = argparse.ArgumentParser(description="deck.html → 16:9 PDF")
    ap.add_argument("deck")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--scale", type=int, default=2, help="множитель разрешения (1-3)")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--chrome", help="путь к Chrome/Chromium")
    ap.add_argument("--keep-png", action="store_true")
    a = ap.parse_args()

    out = a.out or os.path.splitext(a.deck)[0] + ".pdf"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Нужен playwright: pip install playwright img2pdf")
    try:
        import img2pdf
    except ImportError:
        sys.exit("Нужен img2pdf: pip install img2pdf")

    chrome = find_chrome(a.chrome)
    height = round(a.width * 9 / 16)
    tmp = tempfile.mkdtemp(prefix="deckpdf-")
    shots, squeezed = [], []

    with sync_playwright() as pw:
        kw = {"executable_path": chrome} if chrome else {}
        browser = pw.chromium.launch(**kw)
        page = browser.new_page(
            viewport={"width": a.width, "height": height},
            device_scale_factor=max(1, min(3, a.scale)))
        page.goto("file://" + os.path.abspath(a.deck))
        page.wait_for_function("window.__deckReady === true", timeout=15000)
        total = page.evaluate("document.querySelectorAll('.slide').length")
        if not total:
            browser.close()
            sys.exit("В деке нет слайдов.")
        for i in range(total):
            page.evaluate(f"location.hash = {i + 1}; location.reload()")
            page.wait_for_function("window.__deckReady === true", timeout=15000)
            # Ждём, пока доиграют reveal-анимации и счётчики
            page.wait_for_timeout(1400)
            # Ужатый слайд выглядит аккуратно, но текст на нём мельче
            # задуманного — в зале это читается хуже, поэтому сообщаем явно.
            fit = page.evaluate(
                "(document.querySelector('.slide.active') || {}).dataset?.fit || null")
            if fit:
                squeezed.append((i + 1, float(fit)))
            p = os.path.join(tmp, f"s{i + 1:03d}.png")
            page.screenshot(path=p)
            shots.append(p)
            print(f"  слайд {i + 1}/{total}", end="\r", flush=True)
        browser.close()

    with open(out, "wb") as f:
        f.write(img2pdf.convert(shots))
    print(f"\nГотово: {out} — {len(shots)} страниц, {os.path.getsize(out) // 1024} КБ")
    for n, k in squeezed:
        note = "разбейте слайд надвое" if k < 0.85 else "на грани, стоит сократить"
        print(f"  ! слайд {n}: содержимое ужато до {round(k * 100)}% — {note}")

    if a.keep_png:
        dest = os.path.splitext(out)[0] + "-png"
        shutil.rmtree(dest, ignore_errors=True)
        shutil.move(tmp, dest)
        print(f"  PNG-кадры: {dest}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
