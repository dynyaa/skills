#!/usr/bin/env python3
"""Упаковка разобранного бренда в самостоятельный скилл.

    python3 pack_kit.py brand-kit --out . --slug acme-deck

Даёт файл `acme-deck.skill`, который человек ставит одним нажатием и дальше
собирает деки, не разбирая стиль заново и не имея под рукой brand-deck.
Внутри — дизайн-система с уже подставленными токенами бренда, шрифты,
логотипы и оба скрипта сборки.

Смысл в передаче: маркетолог или подрядчик получает готовый инструмент,
а не инструкцию «сначала разберите наши презентации».
"""

import argparse
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(HERE_F := __file__))
ROOT = os.path.dirname(HERE)


def slugify(text):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(text)).strip("-").lower()
    return s or "brand"


SKILL_TMPL = """---
name: {slug}
description: >
  Сборка презентаций в фирменном стиле «{name}»: тёмная/светлая тема бренда,
  {head} в заголовках и {body} в тексте, готовая библиотека компонентов,
  встроенные шрифты и логотипы. На выходе один самодостаточный HTML-файл с
  кликабельной навигацией и экспорт в 16:9 PDF. Используй всегда, когда просят
  сделать, переверстать или дополнить презентацию, слайды, дек или питч
  «{name}» — либо любую презентацию «в нашем стиле», «в фирменном стиле»,
  «как обычно».
---

# Презентации «{name}»

Готовый брендовый кит: дизайн-система, шрифты и ассеты уже внутри. Разбирать
стиль заново не нужно — он зафиксирован в `assets/brand.json`.

## Как собрать дек

1. Напишите слайды в файл `slides.html` — только элементы
   `<section class="slide">…</section>` подряд, без обвязки. Компоненты и
   правила разметки — в `COMPONENTS.md`.
2. Соберите:

```bash
python3 scripts/build_deck.py slides.html --brand assets/brand.json --out deck.html{tagarg}
```

3. Экспортируйте PDF, если нужен файл для рассылки:

```bash
python3 scripts/render_pdf.py deck.html deck.pdf --scale 2
```

Скрипт сам подставит цвета и кегли, встроит шрифты и картинки в base64 и
вложит навигацию. Итоговый HTML открывается без интернета.

## Стиль бренда

| | |
|---|---|
| Режим | {mode} |
| Фон | `{bg}` |
| Текст | `{text}` |
| Акцент | `{accent}` |
| Заголовки | {head} |
| Текст | {body} |
| Шкала | обложка {cover}pt · заголовок {h2}pt · цифра {stat}pt · текст {bodypt}pt |
| Поля | {margin}% ширины слайда |

Значения менять руками не нужно: правьте `assets/brand.json`, и следующая
сборка подхватит изменения. Так дек не разъедется между слайдами.

## Правила, которые держат дек фирменным

- Заголовок только `<h2>`, акцентное слово — `<span class="ac">`. Не красьте
  текст произвольными цветами: акцент один, и он уже в токенах.
- Никаких `px` в разметке. Все отступы — переменные `--gap-*`, иначе слайды
  начнут отличаться друг от друга на глаз.
- Карточки внутри одного слайда одинаковы по структуре: если у одной есть
  подпись, она есть у всех.
- Каждому элементу — `data-r style="--i:N"` в порядке чтения. Это порядок
  появления при показе.
- Текст берите из исходного документа дословно. Придуманный заголовок звучит
  убедительно, но подписывать его придётся человеку.

## Что внутри

- `assets/brand.json` — токены стиля
- `assets/fonts/` — фирменные гарнитуры (встраиваются в дек)
- `assets/media/` — логотипы и изображения из исходных презентаций
- `assets/deck.css`, `assets/deck.js` — движок
- `EXTRACTION.md` — как разобран стиль и что стоит перепроверить
- `COMPONENTS.md` — библиотека компонентов с примерами разметки
"""


def main():
    ap = argparse.ArgumentParser(description="brand-kit → готовый .skill")
    ap.add_argument("kit", help="папка brand-kit с brand.json")
    ap.add_argument("--out", default=".", help="куда положить .skill")
    ap.add_argument("--slug", help="имя скилла (по умолчанию <бренд>-deck)")
    ap.add_argument("--tag", help="подпись в углу слайдов, например сайт")
    a = ap.parse_args()

    brand_path = os.path.join(a.kit, "brand.json")
    if not os.path.exists(brand_path):
        sys.exit(f"Не найден {brand_path}. Сначала запустите extract_style.py.")
    with open(brand_path, encoding="utf-8") as f:
        brand = json.load(f)

    name = brand.get("name") or "Brand"
    slug = a.slug or (slugify(name) + "-deck")
    staging = os.path.join(a.out, slug)
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(os.path.join(staging, "assets"), exist_ok=True)
    os.makedirs(os.path.join(staging, "scripts"), exist_ok=True)

    for sub in ("fonts", "assets/media", "media"):
        src = os.path.join(a.kit, sub)
        if os.path.isdir(src):
            dst = os.path.join(staging, "assets", os.path.basename(sub))
            shutil.copytree(src, dst, dirs_exist_ok=True)
    shutil.copy(brand_path, os.path.join(staging, "assets", "brand.json"))
    for f in ("deck.css", "deck.js"):
        shutil.copy(os.path.join(ROOT, "assets", f), os.path.join(staging, "assets", f))
    for f in ("build_deck.py", "render_pdf.py"):
        shutil.copy(os.path.join(HERE, f), os.path.join(staging, "scripts", f))
    for f in ("EXTRACTION.md",):
        src = os.path.join(a.kit, f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(staging, f))
    comp = os.path.join(ROOT, "references", "components.md")
    if os.path.exists(comp):
        shutil.copy(comp, os.path.join(staging, "COMPONENTS.md"))

    p, t, lay = brand["palette"], brand["typography"], brand.get("layout", {})
    sc = t["scale"]
    tag = a.tag or brand.get("tag")
    with open(os.path.join(staging, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(SKILL_TMPL.format(
            slug=slug, name=name, head=t["heading"], body=t["body"],
            mode="тёмный" if p["mode"] == "dark" else "светлый",
            bg=p["background"], text=p["text"], accent=p["accent"],
            cover=sc.get("cover_pt"), h2=sc.get("h2_pt"),
            stat=sc.get("stat_pt", sc.get("cover_pt")), bodypt=sc.get("body_pt"),
            margin=lay.get("margin_pct", "—"),
            tagarg=f' --tag "{tag}"' if tag else ""))

    out_file = os.path.join(a.out, slug + ".skill")
    with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(staging):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, a.out))

    size = os.path.getsize(out_file)
    print(f"Готово: {out_file} ({size // 1024} КБ)")
    print(f"  папка скилла: {staging}")
    if not os.path.isdir(os.path.join(staging, "assets", "fonts")):
        print("  ! шрифтов в ките нет — деки на чужом компьютере откроются "
              "системной гарнитурой")
    if size > 25 * 1024 * 1024:
        print("  ! больше 25 МБ: уберите лишние изображения из assets/media")


if __name__ == "__main__":
    main()
