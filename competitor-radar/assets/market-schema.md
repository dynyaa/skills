# Схема market.json

Обязательные секции: `meta`, `criteria`, `competitors`. Остальные пропускаются, если пусты, — но дашборд без `findings` и `recommendations` это отчёт без ответа, так что пропускать их стоит только когда данных правда нет.

```
meta
  market        "Сетевые кофейни"              что за рынок
  geo           "Алматы"                       география
  segment       "средний ценовой сегмент"      опционально
  date          "2026-08-19"                   дата снимка, ISO
  our_id        "id своей компании"            из списка competitors. Можно оставить пустым, если разбирается
                                               чужой рынок или пользователь себя не назвал — тогда скажите об этом в отчёте

question        "Ради какого решения делался разбор" — печатается в шапке

criteria[]      порядок колонок таблицы; 6-8 штук — больше не помещается по ширине
  key           "pricing"                      идентификатор, совпадает с ключом в attrs
  label         "Уровень цен"                  заголовок колонки
  hint          опционально: пояснение под заголовком

axes                                            карта позиционирования; без неё карта не рисуется
  x { label, low, high }                        low/high — подписи полюсов словами
  y { label, low, high }

competitors[]
  id            "kofe-boom"
  name          "Coffee Boom"
  role          "us" | "leader" | "player"      влияет на цвет точки и порядок карточек
  one_liner     одно предложение: что продают и кому
  site          "example.kz"
  position      { x: 0..1, y: 0..1, note: "из чего следует позиция" }
  scale         { label: "Точек", value: "17" }  опционально: масштаб игрока
  attrs         { "<criteria.key>": { value, confidence, source, date } }
                value: строка или null (null = данных нет, это честно и видно в дашборде)
                confidence: "confirmed" | "indirect" | "assumption"
  strengths[]   строки
  weaknesses[]  строки
  recent[]      { date, what, source }           2-3 свежих факта
  how_to_win    как выигрывать сделки против него; на потребительских рынках — где он уязвим. Опционально

findings[]      { title, text, based_on }        based_on — на какие данные опирается вывод
gaps[]          { title, text, why_empty }       why_empty — почему место может быть пустым не просто так
recommendations[] { action, why, horizon }
watchlist[]     { what, where }                  что отслеживать в следующих прогонах
sources[]       { title, url, date }
```

## Минимальный валидный пример

```json
{
  "meta": { "market": "Кофейни", "geo": "Алматы", "date": "2026-08-19", "our_id": "we" },
  "question": "Где нам занять место, чтобы не воевать ценой",
  "criteria": [{ "key": "price", "label": "Средний чек" }],
  "competitors": [
    { "id": "we", "name": "Наша сеть", "role": "us",
      "attrs": { "price": { "value": "1 800 ₸", "confidence": "confirmed" } } },
    { "id": "x", "name": "Конкурент X", "role": "leader",
      "attrs": { "price": { "value": null, "confidence": "indirect" } } }
  ]
}
```

Полный пример нужного уровня конкретики — `example-market.json`.
