#!/usr/bin/env python3
"""Сравнение двух снимков market.json: что изменилось на рынке.

    python3 diff_snapshots.py snapshots/2026-08-01.json snapshots/2026-08-19.json --out changes.json

Выдаёт changes.json для build_dashboard.py --changes.
Классифицирует изменения по значимости, чтобы лента не забивалась шумом:
  high   — состав игроков, цены, сегмент/гео, крупный сдвиг позиции
  normal — прочие изменения значений, новые факты
  low    — появились данные там, где было пусто; изменилась только достоверность
"""

import argparse
import json
import sys

HIGH_KEYS = ("price", "pricing", "cost", "tariff", "цена", "segment", "geo", "channel")
POSITION_EPS = 0.15


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"Невалидный JSON в {p}: {e}")


def is_high(key, label):
    hay = (key + " " + (label or "")).lower()
    return any(h in hay for h in HIGH_KEYS)


def diff(old, new):
    changes = []
    o_by = {c.get("id") or c.get("name"): c for c in old.get("competitors") or []}
    n_by = {c.get("id") or c.get("name"): c for c in new.get("competitors") or []}
    labels = {c["key"]: c.get("label", c["key"]) for c in new.get("criteria") or []}

    for cid, c in n_by.items():
        if cid not in o_by:
            changes.append({"severity": "high", "type": "entered",
                            "competitor": c.get("name"),
                            "text": "появился в обзоре — " + (c.get("one_liner") or "новый игрок")})
    for cid, c in o_by.items():
        if cid not in n_by:
            changes.append({"severity": "high", "type": "left",
                            "competitor": c.get("name"),
                            "text": "исчез из обзора — проверьте, ушёл с рынка или просто не нашёлся"})

    for cid, nc in n_by.items():
        oc = o_by.get(cid)
        if not oc:
            continue
        name = nc.get("name")

        # значения критериев
        oa, na = oc.get("attrs") or {}, nc.get("attrs") or {}
        for key in set(list(oa.keys()) + list(na.keys())):
            ov = (oa.get(key) or {}).get("value")
            nv = (na.get(key) or {}).get("value")
            oconf = (oa.get(key) or {}).get("confidence")
            nconf = (na.get(key) or {}).get("confidence")
            label = labels.get(key, key)
            if ov == nv:
                if oconf != nconf and nv not in (None, ""):
                    changes.append({"severity": "low", "type": "confidence",
                                    "competitor": name,
                                    "text": f"{label}: значение то же, достоверность теперь «{nconf}»"})
                continue
            if ov in (None, "") and nv not in (None, ""):
                changes.append({"severity": "low", "type": "filled", "competitor": name,
                                "text": f"{label}: появились данные", "before": None, "after": nv})
            elif nv in (None, "") and ov not in (None, ""):
                changes.append({"severity": "normal", "type": "lost", "competitor": name,
                                "text": f"{label}: данные больше не найдены — возможно, убрали из публичного доступа",
                                "before": ov, "after": None})
            else:
                changes.append({"severity": "high" if is_high(key, label) else "normal",
                                "type": "value", "competitor": name,
                                "text": f"{label} изменился", "before": ov, "after": nv})

        # позиция на карте
        op, np_ = oc.get("position") or {}, nc.get("position") or {}
        for ax in ("x", "y"):
            if isinstance(op.get(ax), (int, float)) and isinstance(np_.get(ax), (int, float)):
                delta = abs(np_[ax] - op[ax])
                if delta >= POSITION_EPS:
                    direction = "вправо/вверх" if np_[ax] > op[ax] else "влево/вниз"
                    changes.append({"severity": "high", "type": "position", "competitor": name,
                                    "text": f"сдвинулся по оси {ax.upper()} на {delta:.2f} ({direction})"})

        # новые факты
        seen = {(r.get("date"), r.get("what")) for r in oc.get("recent") or []}
        for r in nc.get("recent") or []:
            if (r.get("date"), r.get("what")) not in seen:
                changes.append({"severity": "normal", "type": "fact", "competitor": name,
                                "text": f'{r.get("date","")} — {r.get("what","")}'.strip(" —")})

    order = {"high": 0, "normal": 1, "low": 2}
    changes.sort(key=lambda c: order.get(c.get("severity"), 9))
    return {
        "from": (old.get("meta") or {}).get("date"),
        "to": (new.get("meta") or {}).get("date"),
        "changes": changes,
    }


def main():
    ap = argparse.ArgumentParser(description="Дифф двух снимков рынка")
    ap.add_argument("old_json")
    ap.add_argument("new_json")
    ap.add_argument("--out", default="changes.json")
    a = ap.parse_args()

    res = diff(load(a.old_json), load(a.new_json))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    by = {}
    for c in res["changes"]:
        by[c["severity"]] = by.get(c["severity"], 0) + 1
    print(f'Готово: {a.out}')
    print(f'  период: {res["from"]} → {res["to"]}')
    print(f'  изменений: {len(res["changes"])}'
          + (f' (важных: {by.get("high",0)}, обычных: {by.get("normal",0)}, мелких: {by.get("low",0)})'
             if res["changes"] else ""))
    if not res["changes"]:
        print("  рынок не двигался — это нормальный результат, так и напишите в отчёте")


if __name__ == "__main__":
    main()
