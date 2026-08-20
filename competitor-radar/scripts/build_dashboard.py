#!/usr/bin/env python3
"""Сборка интерактивного HTML-дашборда конкурентного анализа из market.json.

    python3 build_dashboard.py market.json --out radar.html
    python3 build_dashboard.py market.json --changes changes.json --out radar.html

Файл самодостаточный: ни шрифтов, ни скриптов извне не грузит.
Палитра и правила разметки взяты из skill `dataviz` и провалидированы
(3 категориальных слота, режим --pairs all, светлая и тёмная тема).
"""

import argparse
import html as htmlmod
import json
import os
import sys

CONF = {
    "confirmed": ("подтверждено", "good"),
    "indirect": ("косвенно", "warning"),
    "assumption": ("оценка", "serious"),
}
ROLE = {
    "us": ("Мы", "s1"),
    "leader": ("Лидер", "s2"),
    "player": ("Игрок", "s3"),
}
SEV = {"high": "critical", "normal": "warning", "low": "muted"}


def esc(x):
    return htmlmod.escape("" if x is None else str(x))


def clip(text, n):
    """Подрезает длинную подпись оси: в SVG текст не переносится сам."""
    t = "" if text is None else str(text)
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def g(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur not in (None, "", [], {}) else default


CSS = """
:root{
  color-scheme:light;
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --good-ink:#006300;
}
@media (prefers-color-scheme:dark){
  :root:where(:not([data-theme="light"])){
    color-scheme:dark;
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --good-ink:#0ca30c;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --good-ink:#0ca30c;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15px;line-height:1.55}
.wrap{max-width:1180px;margin:0 auto;padding:28px 22px 64px}
h1,h2,h3{margin:0;font-weight:700;letter-spacing:-.01em}
h1{font-size:26px;line-height:1.2}
h2{font-size:18px;margin-bottom:12px}
h3{font-size:15px}
a{color:var(--s1)}
p{margin:0 0 10px}
.muted{color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:18px 20px;margin-bottom:18px}
header.top{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:6px}
.crumbs{font-size:13px;color:var(--muted);margin-bottom:6px}
.question{margin-top:12px;padding:12px 14px;border-left:3px solid var(--s1);
  background:var(--surface);border-radius:0 8px 8px 0;font-size:15px}
.question b{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);margin-bottom:3px}
button.theme{background:none;border:1px solid var(--ring);color:var(--ink2);border-radius:8px;
  padding:6px 12px;font-size:13px;cursor:pointer;font-family:inherit}
button.theme:hover{border-color:var(--axis)}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:14px 16px}
.tile .lab{font-size:12px;color:var(--muted);margin-bottom:4px}
.tile .val{font-size:26px;font-weight:700;letter-spacing:-.02em;line-height:1.1}
.tile .sub{font-size:12px;color:var(--muted);margin-top:3px}

.feed li{margin-bottom:9px;padding-left:12px;border-left:3px solid var(--axis);list-style:none}
.feed li.high{border-left-color:var(--critical)}
.feed li.normal{border-left-color:var(--warning)}
.feed ul{padding:0;margin:0}
.feed .who{font-weight:600}
.feed .delta{font-size:13px;color:var(--ink2)}
.feed .delta s{color:var(--muted);text-decoration-thickness:1px}

.mapwrap{position:relative}
svg.map{width:100%;height:auto;display:block;overflow:visible}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--ink2);margin-top:10px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}
.tip{position:absolute;pointer-events:none;opacity:0;transition:opacity .12s;
  background:var(--surface);border:1px solid var(--axis);border-radius:8px;padding:8px 11px;
  font-size:13px;max-width:270px;box-shadow:0 6px 22px rgba(0,0,0,.14);z-index:20}
.tip b{display:block;margin-bottom:2px}

.tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px;font-size:13px}
.tools label{display:inline-flex;align-items:center;gap:6px;cursor:pointer;color:var(--ink2)}
.tools select{font-family:inherit;font-size:13px;padding:5px 8px;border-radius:7px;
  border:1px solid var(--ring);background:var(--surface);color:var(--ink)}
.tablescroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:9px 11px;border-bottom:1px solid var(--grid);vertical-align:top}
thead th{font-size:12px;color:var(--ink2);font-weight:600;border-bottom:1px solid var(--axis);
  position:sticky;top:0;background:var(--surface)}
thead th .hint{display:block;font-weight:400;color:var(--muted);font-size:11px}
tbody tr:hover td{background:color-mix(in srgb,var(--s1) 5%,transparent)}
td.name{font-weight:600;white-space:nowrap}
td.name .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:0}
td.empty{color:var(--muted);font-style:italic}
.badge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  padding:1px 5px;border-radius:4px;margin-left:6px;vertical-align:1px;white-space:nowrap;
  border:1px solid currentColor}
.badge.good{color:var(--good-ink)}
.badge.warning{color:#8a6100}
.badge.serious{color:#a24a22}
:root[data-theme="dark"] .badge.warning{color:var(--warning)}
:root[data-theme="dark"] .badge.serious{color:var(--serious)}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .badge.warning{color:var(--warning)}
 :root:where(:not([data-theme="light"])) .badge.serious{color:var(--serious)}}

.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.comp{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:16px 18px}
.comp.us{border-color:var(--s1);border-width:2px}
.comp .hd{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:4px}
.comp .role{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.comp .one{color:var(--ink2);font-size:14px;margin-bottom:10px}
.comp h4{margin:10px 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:700}
.comp ul{margin:0;padding-left:17px;font-size:13.5px}
.comp li{margin-bottom:3px}
.comp .win{margin-top:10px;padding:9px 11px;background:color-mix(in srgb,var(--s1) 8%,transparent);
  border-radius:7px;font-size:13.5px}
.comp .recent{font-size:12.5px;color:var(--ink2)}
.comp .recent span{color:var(--muted)}

.blocks{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.finding{padding:13px 15px;background:var(--surface);border:1px solid var(--ring);border-radius:10px}
.finding h3{margin-bottom:5px}
.finding .based{font-size:12px;color:var(--muted);margin-top:7px}
.rec{display:flex;gap:12px;padding:12px 0;border-bottom:1px solid var(--grid)}
.rec:last-child{border-bottom:none}
.rec .n{flex:0 0 26px;height:26px;border-radius:50%;background:var(--s1);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700}
.rec .hz{font-size:12px;color:var(--muted);margin-top:2px}
ol.src{font-size:13px;color:var(--ink2);padding-left:20px}
ol.src li{margin-bottom:4px}
footer{margin-top:26px;font-size:12px;color:var(--muted);border-top:1px solid var(--grid);padding-top:12px}
@media print{body{background:#fff}.theme{display:none}}
"""

JS = """
(function(){
  var root=document.documentElement, btn=document.getElementById('themeBtn');
  function label(){var d=root.getAttribute('data-theme')==='dark'||
    (!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme:dark)').matches);
    btn.textContent=d?'Светлая тема':'Тёмная тема';}
  btn.onclick=function(){
    var d=root.getAttribute('data-theme')==='dark'||
      (!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme:dark)').matches);
    root.setAttribute('data-theme',d?'light':'dark'); label();};
  label();

  var tip=document.getElementById('tip'), wrap=document.getElementById('mapwrap');
  if(tip&&wrap){
    wrap.querySelectorAll('[data-tip]').forEach(function(el){
      el.addEventListener('mouseenter',function(e){
        tip.innerHTML=el.getAttribute('data-tip'); tip.style.opacity=1;});
      el.addEventListener('mousemove',function(e){
        var r=wrap.getBoundingClientRect();
        var x=e.clientX-r.left+14, y=e.clientY-r.top+14;
        if(x+280>r.width) x=e.clientX-r.left-286;
        tip.style.left=x+'px'; tip.style.top=y+'px';});
      el.addEventListener('mouseleave',function(){tip.style.opacity=0;});
    });
  }

  var roleSel=document.getElementById('fRole'), confBox=document.getElementById('fConf');
  function apply(){
    var r=roleSel?roleSel.value:'all', onlyConf=confBox?confBox.checked:false;
    document.querySelectorAll('tbody tr[data-role]').forEach(function(tr){
      tr.style.display=(r==='all'||tr.getAttribute('data-role')===r)?'':'none';});
    document.querySelectorAll('td[data-conf]').forEach(function(td){
      var hide=onlyConf&&td.getAttribute('data-conf')!=='confirmed';
      td.querySelectorAll('.cellval').forEach(function(s){s.style.opacity=hide?'.25':'1';});});
    document.querySelectorAll('.comp[data-role]').forEach(function(c){
      c.style.display=(r==='all'||c.getAttribute('data-role')===r)?'':'none';});
  }
  if(roleSel) roleSel.onchange=apply;
  if(confBox) confBox.onchange=apply;
})();
"""


def render_map(d):
    axes = g(d, "axes")
    comps = d.get("competitors") or []
    pts = [c for c in comps if isinstance(g(c, "position", "x"), (int, float))]
    if not axes or not pts:
        return ""
    W, H = 900, 520
    PL, PR, PT, PB = 118, 60, 34, 76
    iw, ih = W - PL - PR, H - PT - PB

    def px(v):
        return PL + float(v) * iw

    def py(v):
        return PT + (1 - float(v)) * ih

    parts = [f'<svg class="map" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Карта позиционирования">']
    # grid
    for i in range(1, 4):
        x = PL + iw * i / 4
        y = PT + ih * i / 4
        parts.append(f'<line x1="{x:.0f}" y1="{PT}" x2="{x:.0f}" y2="{PT+ih}" stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<line x1="{PL}" y1="{y:.0f}" x2="{PL+iw}" y2="{y:.0f}" stroke="var(--grid)" stroke-width="1"/>')
    parts.append(f'<rect x="{PL}" y="{PT}" width="{iw}" height="{ih}" fill="none" stroke="var(--axis)" stroke-width="1"/>')
    # axis labels
    ax, ay = axes.get("x", {}), axes.get("y", {})
    parts.append(f'<text x="{PL}" y="{PT+ih+26}" font-size="12.5" fill="var(--muted)">← {esc(clip(ax.get("low",""), 42))}</text>')
    parts.append(f'<text x="{PL+iw}" y="{PT+ih+26}" font-size="12.5" fill="var(--muted)" text-anchor="end">{esc(clip(ax.get("high",""), 42))} →</text>')
    parts.append(f'<text x="{PL+iw/2}" y="{PT+ih+52}" font-size="13" font-weight="600" fill="var(--ink2)" text-anchor="middle">{esc(ax.get("label",""))}</text>')
    # Подписи полюсов и название оси Y разведены по x, иначе на длинных подписях
    # они наезжают друг на друга — в вертикальном тексте это особенно незаметно
    # до самого рендера, поэтому длинные полюса ещё и подрезаются.
    parts.append(f'<text transform="translate({PL-26},{PT+ih}) rotate(-90)" font-size="12.5" fill="var(--muted)">← {esc(clip(ay.get("low",""), 34))}</text>')
    parts.append(f'<text transform="translate({PL-26},{PT}) rotate(-90)" font-size="12.5" fill="var(--muted)" text-anchor="end">{esc(clip(ay.get("high",""), 34))} →</text>')
    parts.append(f'<text transform="translate({PL-62},{PT+ih/2}) rotate(-90)" font-size="13" font-weight="600" fill="var(--ink2)" text-anchor="middle">{esc(clip(ay.get("label",""), 40))}</text>')

    for c in pts:
        role = c.get("role", "player")
        var = ROLE.get(role, ROLE["player"])[1]
        x, y = px(g(c, "position", "x", default=0.5)), py(g(c, "position", "y", default=0.5))
        r = 11 if role == "us" else 8
        tip = f'<b>{esc(c.get("name"))}</b>{esc(c.get("one_liner") or "")}'
        note = g(c, "position", "note")
        if note:
            tip += f'<br><span style="color:var(--muted)">{esc(note)}</span>'
        flip = x > PL + iw * 0.72
        lx = x - r - 8 if flip else x + r + 8
        anchor = "end" if flip else "start"
        weight = "700" if role == "us" else "600"
        parts.append(f'<g data-tip="{htmlmod.escape(tip, quote=True)}" style="cursor:default">')
        # 2px surface ring so overlapping marks stay separable
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r+2}" fill="var(--surface)"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="var(--{var})"/>')
        if role == "us":
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r+5}" fill="none" stroke="var(--{var})" stroke-width="1.5" opacity=".45"/>')
        parts.append(f'<text x="{lx:.1f}" y="{y+4:.1f}" font-size="12.5" font-weight="{weight}" '
                     f'fill="var(--ink)" text-anchor="{anchor}">{esc(c.get("name"))}</text>')
        parts.append("</g>")
    parts.append("</svg>")

    legend = "".join(
        f'<span><i style="background:var(--{v[1]})"></i>{esc(v[0])}</span>'
        for k, v in ROLE.items()
        if any(c.get("role", "player") == k for c in pts)
    )
    return (f'<div class="card"><h2>Карта позиционирования</h2>'
            f'<div class="mapwrap" id="mapwrap">{"".join(parts)}'
            f'<div class="tip" id="tip"></div></div>'
            f'<div class="legend">{legend}</div></div>')


def render_table(d):
    crit = d.get("criteria") or []
    comps = d.get("competitors") or []
    if not crit or not comps:
        return ""
    head = "".join(
        f'<th>{esc(c.get("label"))}'
        + (f'<span class="hint">{esc(c["hint"])}</span>' if c.get("hint") else "")
        + "</th>"
        for c in crit
    )
    rows = []
    for c in comps:
        var = ROLE.get(c.get("role", "player"), ROLE["player"])[1]
        cells = []
        for cr in crit:
            a = (c.get("attrs") or {}).get(cr["key"]) or {}
            val = a.get("value")
            if val in (None, ""):
                cells.append('<td class="empty" data-conf="none">нет данных</td>')
                continue
            conf = a.get("confidence", "indirect")
            lab, tone = CONF.get(conf, CONF["indirect"])
            src = a.get("source") or ""
            date = a.get("date") or ""
            title = " · ".join(x for x in [src, date] if x)
            badge = "" if conf == "confirmed" else f'<span class="badge {tone}">{lab}</span>'
            cells.append(
                f'<td data-conf="{esc(conf)}"{f" title={json.dumps(title, ensure_ascii=False)}" if title else ""}>'
                f'<span class="cellval">{esc(val)}{badge}</span></td>'
            )
        rows.append(
            f'<tr data-role="{esc(c.get("role","player"))}">'
            f'<td class="name"><span class="dot" style="background:var(--{var})"></span>{esc(c.get("name"))}</td>'
            + "".join(cells) + "</tr>"
        )
    return f"""<div class="card"><h2>Сравнение</h2>
<div class="tools">
  <label>Показать:
    <select id="fRole"><option value="all">все игроки</option>
      <option value="us">только нас</option><option value="leader">лидеров</option>
      <option value="player">остальных</option></select></label>
  <label><input type="checkbox" id="fConf"> приглушить неподтверждённое</label>
  <span class="muted">наведите на ячейку — источник и дата</span>
</div>
<div class="tablescroll"><table><thead><tr><th>Компания</th>{head}</tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></div>"""


def render_cards(d):
    comps = d.get("competitors") or []
    if not comps:
        return ""
    order = {"us": 0, "leader": 1, "player": 2}
    cards = []
    for c in sorted(comps, key=lambda x: order.get(x.get("role", "player"), 9)):
        role = c.get("role", "player")
        rl = ROLE.get(role, ROLE["player"])
        blocks = []
        if c.get("strengths"):
            blocks.append("<h4>Сильные стороны</h4><ul>"
                          + "".join(f"<li>{esc(s)}</li>" for s in c["strengths"]) + "</ul>")
        if c.get("weaknesses"):
            blocks.append("<h4>Слабые места</h4><ul>"
                          + "".join(f"<li>{esc(s)}</li>" for s in c["weaknesses"]) + "</ul>")
        if c.get("recent"):
            items = "".join(
                f'<li class="recent"><span>{esc(r.get("date"))}</span> — {esc(r.get("what"))}</li>'
                for r in c["recent"])
            blocks.append(f"<h4>Что происходит</h4><ul>{items}</ul>")
        if c.get("how_to_win"):
            blocks.append(f'<div class="win"><b>Как выигрывать:</b> {esc(c["how_to_win"])}</div>')
        scale = g(c, "scale")
        scale_html = (f'<div class="muted" style="font-size:12.5px">'
                      f'{esc(scale.get("label"))}: <b>{esc(scale.get("value"))}</b></div>'
                      if scale else "")
        cards.append(
            f'<div class="comp {"us" if role=="us" else ""}" data-role="{esc(role)}">'
            f'<div class="hd"><h3>{esc(c.get("name"))}</h3><span class="role">{esc(rl[0])}</span></div>'
            f'<div class="one">{esc(c.get("one_liner") or "")}</div>{scale_html}'
            + "".join(blocks) + "</div>"
        )
    return f'<h2 style="margin:24px 0 12px">Игроки</h2><div class="cards">{"".join(cards)}</div>'


def render_changes(ch):
    if not ch or not ch.get("changes"):
        return ""
    items = []
    for c in ch["changes"]:
        sev = c.get("severity", "normal")
        delta = ""
        if c.get("before") is not None or c.get("after") is not None:
            delta = (f'<div class="delta"><s>{esc(c.get("before") or "нет данных")}</s> → '
                     f'<b>{esc(c.get("after") or "нет данных")}</b></div>')
        items.append(f'<li class="{esc(sev)}"><span class="who">{esc(c.get("competitor") or "рынок")}</span> — '
                     f'{esc(c.get("text"))}{delta}</li>')
    period = ""
    if ch.get("from") and ch.get("to"):
        period = f'<span class="muted" style="font-size:13px"> · {esc(ch["from"])} → {esc(ch["to"])}</span>'
    return (f'<div class="card feed"><h2>Что изменилось{period}</h2>'
            f'<ul>{"".join(items)}</ul></div>')


def render_tiles(d, ch):
    comps = d.get("competitors") or []
    crit = d.get("criteria") or []
    total = len(comps) * len(crit)
    filled = conf = 0
    for c in comps:
        for cr in crit:
            a = (c.get("attrs") or {}).get(cr["key"]) or {}
            if a.get("value") not in (None, ""):
                filled += 1
                if a.get("confidence") == "confirmed":
                    conf += 1
    tiles = [("Игроков в обзоре", str(len(comps)), esc(g(d, "meta", "segment", default="") or ""))]
    if total:
        tiles.append(("Данные собраны", f"{round(100*filled/total)}%",
                      f"{total-filled} ячеек без данных"))
        tiles.append(("Из них подтверждено", f"{round(100*conf/filled) if filled else 0}%",
                      "остальное — косвенно и оценки"))
    if ch and ch.get("changes"):
        highs = sum(1 for c in ch["changes"] if c.get("severity") == "high")
        tiles.append(("Изменений с прошлого раза", str(len(ch["changes"])),
                      f"из них важных: {highs}"))
    else:
        tiles.append(("Дата снимка", esc(g(d, "meta", "date", default="—")), "точка отсчёта для мониторинга"))
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="lab">{esc(t[0])}</div><div class="val">{esc(t[1])}</div>'
        f'<div class="sub">{esc(t[2])}</div></div>' for t in tiles) + "</div>"


def render(d, ch=None):
    meta = d.get("meta") or {}
    crumbs = " · ".join(esc(x) for x in [meta.get("geo"), meta.get("segment"), meta.get("date")] if x)
    title = esc(meta.get("market") or "Конкурентный анализ")

    out = [f'<header class="top"><div><div class="crumbs">{crumbs}</div>'
           f'<h1>Радар рынка: {title}</h1></div>'
           f'<button class="theme" id="themeBtn">Тёмная тема</button></header>']
    if d.get("question"):
        out.append(f'<div class="question"><b>Вопрос, на который отвечает разбор</b>{esc(d["question"])}</div>')
    out.append('<div style="height:18px"></div>')
    out.append(render_tiles(d, ch))
    out.append(render_changes(ch))
    out.append(render_map(d))
    out.append(render_table(d))

    if d.get("findings"):
        cards = "".join(
            f'<div class="finding"><h3>{esc(f.get("title"))}</h3><p>{esc(f.get("text"))}</p>'
            + (f'<div class="based">Опирается на: {esc(f["based_on"])}</div>' if f.get("based_on") else "")
            + "</div>" for f in d["findings"])
        out.append(f'<h2 style="margin:24px 0 12px">Выводы</h2><div class="blocks">{cards}</div>')

    if d.get("gaps"):
        cards = "".join(
            f'<div class="finding"><h3>{esc(gp.get("title"))}</h3><p>{esc(gp.get("text"))}</p>'
            + (f'<div class="based">Почему может быть пусто: {esc(gp["why_empty"])}</div>'
               if gp.get("why_empty") else "") + "</div>" for gp in d["gaps"])
        out.append(f'<h2 style="margin:24px 0 12px">Незанятые места</h2><div class="blocks">{cards}</div>')

    if d.get("recommendations"):
        recs = "".join(
            f'<div class="rec"><div class="n">{i}</div><div><b>{esc(r.get("action"))}</b>'
            f'<div style="font-size:13.5px;color:var(--ink2)">{esc(r.get("why"))}</div>'
            + (f'<div class="hz">Горизонт: {esc(r["horizon"])}</div>' if r.get("horizon") else "")
            + "</div></div>" for i, r in enumerate(d["recommendations"], 1))
        out.append(f'<div class="card"><h2>Что делать</h2>{recs}</div>')

    out.append(render_cards(d))

    if d.get("watchlist"):
        items = "".join(f'<li>{esc(w.get("what"))} <span class="muted">— {esc(w.get("where"))}</span></li>'
                        for w in d["watchlist"])
        out.append(f'<div class="card"><h2>Держим на радаре</h2><ul>{items}</ul></div>')

    if d.get("sources"):
        srcs = []
        for s in d["sources"]:
            title = esc(s.get("title") or s.get("url") or "источник")
            if s.get("url"):
                title = '<a href="' + esc(s["url"]) + '" rel="noreferrer">' + title + "</a>"
            if s.get("date"):
                title += ' <span class="muted">· ' + esc(s["date"]) + "</span>"
            srcs.append("<li>" + title + "</li>")
        out.append('<div class="card"><h2>Источники</h2><ol class="src">'
                   + "".join(srcs) + "</ol></div>")

    out.append(f'<footer>Собрано автоматически из открытых источников на {esc(meta.get("date") or "")}. '
               f'Значения с бейджами «косвенно» и «оценка» требуют проверки перед решением. '
               f'Пустые ячейки означают, что данных не нашлось, — а не что их нет.</footer>')

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Радар рынка: {title}</title><style>{CSS}</style></head>
<body><div class="wrap">{"".join(out)}</div><script>{JS}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="HTML-дашборд конкурентного анализа")
    ap.add_argument("market_json")
    ap.add_argument("--changes", help="changes.json от diff_snapshots.py")
    ap.add_argument("--out", default="radar.html")
    a = ap.parse_args()

    try:
        with open(a.market_json, encoding="utf-8") as f:
            d = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"Невалидный JSON в {a.market_json}: {e}")
    for req in ("meta", "criteria", "competitors"):
        if req not in d:
            sys.exit(f"Нет обязательной секции '{req}'. Схема — assets/market-schema.md")

    ch = None
    if a.changes and os.path.exists(a.changes):
        with open(a.changes, encoding="utf-8") as f:
            ch = json.load(f)

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render(d, ch))

    comps = d["competitors"]
    crit = d["criteria"]
    total = len(comps) * len(crit)
    empty = sum(1 for c in comps for cr in crit
                if ((c.get("attrs") or {}).get(cr["key"]) or {}).get("value") in (None, ""))
    assume = sum(1 for c in comps for cr in crit
                 if ((c.get("attrs") or {}).get(cr["key"]) or {}).get("confidence") == "assumption")
    print(f"Готово: {a.out} ({os.path.getsize(a.out)//1024} КБ)")
    print(f"  игроков: {len(comps)}, критериев: {len(crit)}")
    print(f"  ячеек без данных: {empty} из {total}")
    print(f"  значений-оценок (assumption): {assume}")
    if not d.get("findings"):
        print("  ! нет секции findings — дашборд описывает рынок, но ничего не отвечает")
    if not d.get("recommendations"):
        print("  ! нет секции recommendations")
    if not any(c.get("role") == "us" for c in comps):
        print("  · в списке нет своей компании (role: us) — карта не покажет, где вы."
              " Это нормально для обзора чужого рынка, но если разбор для себя, добавьте её")
    if len(crit) > 7:
        print(f"  · критериев {len(crit)}: таблица уйдёт в горизонтальную прокрутку."
              " Комфортно помещается 6-7 — лишнее лучше вынести в карточки игроков")


if __name__ == "__main__":
    main()
