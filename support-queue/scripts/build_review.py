#!/usr/bin/env python3
"""Страница проверки черновиков ответов + выгрузка для импорта обратно.

    python3 build_review.py processed.json --out review.html --csv answers.csv

Порядок на странице неслучаен: эскалации и низкая уверенность идут первыми —
это то, что действительно требует человека. Остальное просматривается бегло.
"""

import argparse
import csv
import html as htmlmod
import json
import os
import sys

DECISION = {
    "escalate": ("На человека", "critical"),
    "answer_with_caveat": ("Ответ с оговоркой", "warning"),
    "answer": ("Готов к отправке", "good"),
    "no_reply": ("Без ответа", "muted"),
}
CONFIDENCE = {"high": "высокая", "medium": "средняя", "low": "низкая"}
URGENCY = {"high": ("срочно", "critical"), "normal": ("", ""), "low": ("", "")}


def esc(x):
    return htmlmod.escape("" if x is None else str(x))


def nl(x):
    return esc(x).replace("\n", "<br>")


CSS = """
:root{color-scheme:light;
 --plane:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
 --s1:#2a78d6;--good:#0ca30c;--warning:#fab219;--critical:#d03b3b;--good-ink:#006300;
 --warn-ink:#8a6100;--crit-ink:#a32020}
@media(prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
 --plane:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--s1:#3987e5;
 --good-ink:#0ca30c;--warn-ink:#fab219;--crit-ink:#e07070}}
:root[data-theme="dark"]{color-scheme:dark;
 --plane:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--s1:#3987e5;
 --good-ink:#0ca30c;--warn-ink:#fab219;--crit-ink:#e07070}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
 font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15px;line-height:1.55}
.wrap{max-width:1000px;margin:0 auto;padding:26px 20px 64px}
h1{font-size:24px;margin:0;letter-spacing:-.01em}
h2{font-size:17px;margin:26px 0 12px}
.crumbs{font-size:13px;color:var(--muted);margin-bottom:5px}
header.top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
button.theme{background:none;border:1px solid var(--ring);color:var(--ink2);border-radius:8px;
 padding:6px 12px;font-size:13px;cursor:pointer;font-family:inherit}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:11px;margin:18px 0}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:11px;padding:13px 15px}
.tile .lab{font-size:12px;color:var(--muted);margin-bottom:3px}
.tile .val{font-size:25px;font-weight:700;letter-spacing:-.02em;line-height:1.1}
.tile .sub{font-size:12px;color:var(--muted);margin-top:2px}
.tile.alert .val{color:var(--crit-ink)}
.notes{background:var(--surface);border:1px solid var(--ring);border-left:3px solid var(--s1);
 border-radius:0 11px 11px 0;padding:13px 16px;margin-bottom:16px;font-size:14.5px;color:var(--ink2)}
.gaps{background:var(--surface);border:1px solid var(--ring);border-left:3px solid var(--warning);
 border-radius:0 11px 11px 0;padding:14px 17px;margin-bottom:18px}
.gaps h3{margin:0 0 6px;font-size:15px}
.gaps ul{margin:0;padding-left:19px;font-size:14px;color:var(--ink2)}
.gaps p{margin:8px 0 0;font-size:12.5px;color:var(--muted)}
.tools{display:flex;gap:12px;flex-wrap:wrap;align-items:center;font-size:13px;
 position:sticky;top:0;background:var(--plane);padding:10px 0;z-index:5;border-bottom:1px solid var(--grid)}
.tools select,.tools input[type=search]{font-family:inherit;font-size:13px;padding:5px 9px;
 border-radius:7px;border:1px solid var(--ring);background:var(--surface);color:var(--ink)}
.t{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:16px 18px;margin-bottom:13px}
.t.escalate{border-left:3px solid var(--critical)}
.t.answer_with_caveat{border-left:3px solid var(--warning)}
.t.answer{border-left:3px solid var(--good)}
.t.no_reply{border-left:3px solid var(--axis);opacity:.72}
.t .hd{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
.t .who{font-weight:600}
.t .meta{font-size:12.5px;color:var(--muted)}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 10px}
.chip{font-size:11px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;
 padding:2px 7px;border-radius:5px;border:1px solid currentColor;color:var(--muted)}
.chip.good{color:var(--good-ink)}.chip.warning{color:var(--warn-ink)}.chip.critical{color:var(--crit-ink)}
.chip.topic{color:var(--s1)}
.msg{background:color-mix(in srgb,var(--ink) 4%,transparent);border-radius:9px;padding:11px 13px;
 font-size:14px;color:var(--ink2);white-space:normal}
.msg .sub{font-weight:600;color:var(--ink);display:block;margin-bottom:3px}
.draft{margin-top:11px;border:1px solid var(--axis);border-radius:9px;padding:12px 14px;font-size:14.5px}
.draft .cap{display:flex;justify-content:space-between;align-items:center;
 font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
 font-weight:700;margin-bottom:7px}
.draft button{background:none;border:1px solid var(--ring);color:var(--ink2);border-radius:6px;
 padding:3px 9px;font-size:11px;cursor:pointer;font-family:inherit;text-transform:none;letter-spacing:0}
.draft button:hover{border-color:var(--s1);color:var(--s1)}
.refs{margin-top:9px;font-size:12.5px;color:var(--muted)}
.refs b{color:var(--ink2);font-weight:600}
.brief{margin-top:11px;background:color-mix(in srgb,var(--critical) 7%,transparent);
 border-radius:9px;padding:12px 14px;font-size:14px}
.brief .cap{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--crit-ink);
 font-weight:700;margin-bottom:6px}
.brief dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:3px 10px}
.brief dt{color:var(--muted);font-size:12.5px}
.brief dd{margin:0}
.gap-note{margin-top:9px;font-size:12.5px;color:var(--warn-ink)}
footer{margin-top:28px;font-size:12px;color:var(--muted);border-top:1px solid var(--grid);padding-top:12px}
.empty{color:var(--muted);font-style:italic;padding:20px 0}
"""

JS = """
(function(){
 var root=document.documentElement,btn=document.getElementById('themeBtn');
 function lab(){var d=root.getAttribute('data-theme')==='dark'||
   (!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme:dark)').matches);
   btn.textContent=d?'Светлая тема':'Тёмная тема';}
 btn.onclick=function(){var d=root.getAttribute('data-theme')==='dark'||
   (!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme:dark)').matches);
   root.setAttribute('data-theme',d?'light':'dark');lab();};lab();

 document.querySelectorAll('[data-copy]').forEach(function(b){
   b.onclick=function(){
     var t=document.getElementById(b.getAttribute('data-copy')).innerText;
     navigator.clipboard.writeText(t).then(function(){
       var o=b.textContent;b.textContent='скопировано';setTimeout(function(){b.textContent=o;},1400);
     },function(){b.textContent='не вышло — выделите вручную';});};});

 var dSel=document.getElementById('fDec'),tSel=document.getElementById('fTopic'),
     q=document.getElementById('fQ'),count=document.getElementById('shown');
 function apply(){
   var d=dSel.value,t=tSel.value,s=(q.value||'').toLowerCase(),n=0;
   document.querySelectorAll('.t').forEach(function(el){
     var ok=(d==='all'||el.dataset.decision===d)&&(t==='all'||el.dataset.topic===t)&&
            (!s||el.innerText.toLowerCase().indexOf(s)>-1);
     el.style.display=ok?'':'none'; if(ok)n++;});
   count.textContent=n;}
 [dSel,tSel].forEach(function(el){el.onchange=apply;});
 q.oninput=apply; apply();
})();
"""


def render(d):
    meta = d.get("meta") or {}
    tickets = d.get("tickets") or []
    summary = d.get("summary") or {}

    order = {"escalate": 0, "answer_with_caveat": 1, "answer": 2, "no_reply": 4}

    def rank(t):
        # Низкая уверенность поднимает обращение наверх независимо от решения:
        # спорный «ответ с оговоркой» требует человека не меньше, чем спорный ответ.
        base = order.get(t.get("decision", "answer"), 3)
        if t.get("confidence") == "low":
            base = min(base, 0.9)
        if t.get("urgency") == "high":
            base -= 0.5
        return base

    tickets = sorted(tickets, key=rank)

    n_esc = sum(1 for t in tickets if t.get("decision") == "escalate")
    n_skip = sum(1 for t in tickets if t.get("decision") == "no_reply")
    n_low = sum(1 for t in tickets if t.get("confidence") == "low"
                and t.get("decision") not in ("escalate", "no_reply"))
    # Плитки должны в сумме давать весь прогон, иначе читатель гадает, куда делись
    # остальные: «готовы» — это всё, что не эскалация и не спорный случай.
    n_ready = len(tickets) - n_esc - n_low - n_skip
    handled = len(tickets) - n_skip
    share = round(100 * (handled - n_esc) / handled) if handled else 0

    tiles = [
        ("Обращений в прогоне", str(len(tickets)),
         esc(meta.get("period") or "") + (f" · без ответа: {n_skip}" if n_skip else "")),
        ("Готовы к отправке", str(n_ready), "просмотреть бегло"),
        ("Требуют человека", str(n_esc + n_low), f"эскалаций: {n_esc}, спорных: {n_low}", n_esc + n_low > 0),
        ("Закрыто без человека", f"{share}%", "доля от прогона"),
    ]
    tiles_html = "".join(
        f'<div class="tile{" alert" if len(t) > 3 and t[3] else ""}">'
        f'<div class="lab">{esc(t[0])}</div><div class="val">{esc(t[1])}</div>'
        f'<div class="sub">{esc(t[2])}</div></div>' for t in tiles)

    notes_html = (f'<div class="notes">{nl(summary["notes"])}</div>'
                  if summary.get("notes") else "")
    gaps = summary.get("kb_gaps") or [t["kb_gap"] for t in tickets if t.get("kb_gap")]
    gaps_html = ""
    if gaps:
        seen, uniq = set(), []
        for gitem in gaps:
            key = gitem if isinstance(gitem, str) else gitem.get("question", "")
            if key and key not in seen:
                seen.add(key)
                uniq.append(key)
        gaps_html = (f'<div class="gaps"><h3>Чего не хватило в базе знаний — {len(uniq)}</h3>'
                     f'<ul>{"".join(f"<li>{esc(x)}</li>" for x in uniq)}</ul>'
                     f'<p>Допишите эти разделы — и в следующий прогон такие обращения закроются '
                     f'без человека. Это и есть способ поднять долю автоматических ответов.</p></div>')

    topics = sorted({t.get("topic") for t in tickets if t.get("topic")})
    topic_opts = "".join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in topics)

    cards = []
    for i, t in enumerate(tickets):
        dec = t.get("decision", "answer")
        dl, dtone = DECISION.get(dec, DECISION["answer"])
        chips = [f'<span class="chip {dtone}">{esc(dl)}</span>']
        if t.get("topic"):
            chips.append(f'<span class="chip topic">{esc(t["topic"])}</span>')
        if t.get("urgency") == "high":
            chips.append('<span class="chip critical">срочно</span>')
        if t.get("type"):
            chips.append(f'<span class="chip">{esc(t["type"])}</span>')
        conf = t.get("confidence")
        if conf and conf != "high":
            chips.append(f'<span class="chip{" warning" if conf=="low" else ""}">'
                         f'уверенность: {esc(CONFIDENCE.get(conf, conf))}</span>')

        who = t.get("customer") or t.get("email") or "клиент"
        meta_line = " · ".join(esc(x) for x in [t.get("id"), t.get("created"), t.get("channel")] if x)

        body = [f'<div class="hd"><span class="who">{esc(who)}</span>'
                f'<span class="meta">{meta_line}</span></div>',
                f'<div class="chips">{"".join(chips)}</div>',
                '<div class="msg">'
                + (f'<span class="sub">{esc(t["subject"])}</span>' if t.get("subject") else "")
                + nl(t.get("text")) + "</div>"]

        if t.get("draft"):
            did = f"d{i}"
            body.append(
                f'<div class="draft"><div class="cap"><span>Черновик ответа</span>'
                f'<button data-copy="{did}">копировать</button></div>'
                f'<div id="{did}">{nl(t["draft"])}</div></div>')
        if t.get("kb_refs"):
            refs = ", ".join(esc(r.get("title") if isinstance(r, dict) else r) for r in t["kb_refs"])
            body.append(f'<div class="refs"><b>Основание в базе:</b> {refs}</div>')
        elif dec not in ("escalate", "no_reply"):
            body.append('<div class="refs"><b>Основание в базе:</b> не указано — проверьте вручную</div>')

        e = t.get("escalation") or {}
        if dec == "escalate" or e:
            rows = []
            for lab, key in (("Суть", "reason"), ("Кому", "to"), ("Что решить", "what"),
                             ("Приоритет", "priority")):
                if e.get(key):
                    rows.append(f"<dt>{lab}</dt><dd>{nl(e[key])}</dd>")
            brief = e.get("brief")
            if brief:
                rows.append(f"<dt>Контекст</dt><dd>{nl(brief)}</dd>")
            body.append('<div class="brief"><div class="cap">Передать менеджеру</div>'
                        f'<dl>{"".join(rows)}</dl></div>' if rows else
                        '<div class="brief"><div class="cap">Передать менеджеру</div>'
                        '<div>Справка не заполнена — менеджеру придётся читать переписку.</div></div>')
        if t.get("kb_gap"):
            body.append(f'<div class="gap-note">Пробел в базе: {esc(t["kb_gap"])}</div>')

        cards.append(f'<div class="t {esc(dec)}" data-decision="{esc(dec)}" '
                     f'data-topic="{esc(t.get("topic") or "")}">{"".join(body)}</div>')

    company = esc(meta.get("company") or "")
    crumbs = " · ".join(esc(x) for x in [company, meta.get("source"), meta.get("run_at")] if x)

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Проверка ответов поддержки{" — " + company if company else ""}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header class="top"><div><div class="crumbs">{crumbs}</div>
<h1>Черновики ответов на проверку</h1></div>
<button class="theme" id="themeBtn">Тёмная тема</button></header>
<div class="tiles">{tiles_html}</div>
{notes_html}
{gaps_html}
<div class="tools">
 <label>Решение: <select id="fDec"><option value="all">все</option>
  <option value="escalate">на человека</option>
  <option value="answer_with_caveat">с оговоркой</option>
  <option value="answer">готовые</option>
  <option value="no_reply">без ответа</option></select></label>
 <label>Тема: <select id="fTopic"><option value="all">все</option>{topic_opts}</select></label>
 <input type="search" id="fQ" placeholder="поиск по тексту">
 <span class="muted">показано: <b id="shown">0</b> из {len(tickets)}</span>
</div>
{"".join(cards) if cards else '<div class="empty">Обращений в прогоне нет.</div>'}
<footer>Ответы подготовлены автоматически на основе базы знаний компании и просмотра не проходили.
Перед отправкой проверьте всё, что касается денег, сроков и обязательств.
Пометка «основание в базе не указано» означает, что ответ не удалось привязать к разделу —
такие проверяйте в первую очередь.</footer>
</div><script>{JS}</script></body></html>"""


def write_csv(d, path):
    rows = []
    for t in d.get("tickets") or []:
        e = t.get("escalation") or {}
        rows.append({
            "id": t.get("id", ""),
            "клиент": t.get("customer") or t.get("email") or "",
            "тема": t.get("topic", ""),
            "решение": DECISION.get(t.get("decision", "answer"), ("", ""))[0],
            "уверенность": CONFIDENCE.get(t.get("confidence", ""), ""),
            "ответ": t.get("draft", ""),
            "основание": "; ".join(
                (r.get("title") if isinstance(r, dict) else str(r))
                for r in (t.get("kb_refs") or [])),
            "кому передать": e.get("to", ""),
            "суть эскалации": e.get("reason", ""),
            "пробел в базе": t.get("kb_gap", ""),
        })
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        if not rows:
            f.write("")
            return
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Страница проверки черновиков ответов")
    ap.add_argument("processed_json")
    ap.add_argument("--out", default="review.html")
    ap.add_argument("--csv", help="дополнительно выгрузить CSV для импорта в хелпдеск")
    a = ap.parse_args()

    try:
        with open(a.processed_json, encoding="utf-8") as f:
            d = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"Невалидный JSON в {a.processed_json}: {e}")
    if "tickets" not in d:
        sys.exit("Нет секции 'tickets'. Схема — assets/processed-schema.md")

    outdir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(outdir, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render(d))
    made = [a.out]
    if a.csv:
        write_csv(d, a.csv)
        made.append(a.csv)

    ts = d["tickets"]
    esc_n = sum(1 for t in ts if t.get("decision") == "escalate")
    low = sum(1 for t in ts if t.get("confidence") == "low" and t.get("decision") != "escalate")
    norefs = sum(1 for t in ts
                 if t.get("decision") not in ("escalate", "no_reply") and not t.get("kb_refs"))
    print("Готово:")
    for m in made:
        print(f"  {m} ({os.path.getsize(m)//1024} КБ)")
    print(f"  обращений: {len(ts)}, на человека: {esc_n}, спорных: {low}")
    skip = sum(1 for t in ts if t.get("decision") == "no_reply")
    handled = len(ts) - skip
    if handled:
        print(f"  закрыто без человека: {round(100*(handled-esc_n)/handled)}%"
              + (f" (без ответа оставлено: {skip})" if skip else ""))
    if norefs:
        print(f"  ! ответов без ссылки на базу знаний: {norefs} — проверьте, не выдуманы ли они")
    gaps = {t["kb_gap"] for t in ts if t.get("kb_gap")}
    if gaps:
        print(f"  пробелов в базе знаний: {len(gaps)}")


if __name__ == "__main__":
    main()
