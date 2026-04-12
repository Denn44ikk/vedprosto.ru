**Eco Fee**

Источник данных сейчас один: [Расчет экосбора.xlsx](./Расчет%20экосбора.xlsx).

Слой разделен на две части:
- `app/storage/knowledge/catalogs/eco_fee`
  Parser книги, sync в Postgres, runtime read активного каталога.
- `app/calculations/eco_fee`
  Match/lookups/calc поверх уже загруженного каталога.

**Что читается из книги**
- ставки по годам: лист с маркером `2025-2027`
- коэффициенты извлечения: листы `извлечения 2025`, `извлечения 2026`
- нормативы товаров: лист `товаров`
- нормативы упаковки: лист `упаковки`
- курс USD: лист `Курсы валют`
- карта `ТН ВЭД -> eco group`: лист с маркером `2414`
- лист `Правила`
  Сейчас используется как человеческая инструкция по структуре файла; в самой формуле расчета не участвует.

**Что хранится в Postgres**
- `eco_fee_meta`
  Активный источник, hash книги, поддерживаемые годы, курс USD из книги, словарь `footnotes_json`.
- `eco_fee_groups`
  Ставка, коэффициент сложности и норматив по группе и году.
- `eco_fee_packaging_norms`
  Норматив упаковки по году.
- `eco_fee_map_entries`
  Карта `ТН ВЭД -> eco group`, исходные строки книги и `footnote_refs_json`.

Текущий режим обновления:
- рабочие таблицы перезаписываются полностью
- отдельные revision-таблицы пока не ведем

**Как обновлять**
1. Заменить `Расчет экосбора.xlsx` в этой папке.
2. Выполнить:

```bash
python -m app.storage.knowledge.catalogs.eco_fee.updater
```

Если нужен явный путь:

```bash
python -m app.storage.knowledge.catalogs.eco_fee.updater --xlsx "app\\storage\\knowledge\\catalogs\\eco_fee\\Расчет экосбора.xlsx"
```

Источник DB URL:
- сначала `ECO_FEE_DB_URL`
- если он не задан, fallback в `TG_DB_URL`

**Runtime payload**
Для UI и будущего TG используется один и тот же packet `eco.by_code`.

На верхнем уровне по коду лежит:
- `default_year`
- `supported_years`
- `selected_year`
- `status`
- `short_text`
- `names_text`
- `years[]`

По каждому году в `years[]`:
- `status`
- `note`
- `preview`
- `usd_rate`
- `packaging_norm`
- `matches_count`
- `best_match`
- `matches[]`

По каждому match:
- `eco_group_code`
- `eco_group_name`
- `match_kind`
- `matched_digits_length`
- `source_rows`
- `matched_codes`
- `examples`
- `db_entries`
- `footnotes`
- `rate_rub_per_kg`
- `complexity_coeff`
- `utilization_norm`
- `surcharge_usd_per_kg`

Это позволяет одним и тем же backend-данным строить три уровня вывода:
- коротко: `ЭКО x.xx`
- средне: `ЭКО x.xx + наименования`
- полно: вся сводка из БД

**Текущие правила**
- базовый год сейчас `2026`
- UI может переключаться между `2025 / 2026 / 2027`
- TG потом должен использовать тот же packet, только через свой formatter
- в UI оператор видит все `examples`, а также первые `10` raw-строк из БД через `db_entries`
- для подсказок UI отдельно берет `GET /api/eco-fee/currency-rates` и показывает `USD / EUR` по ЦБ РФ
  сам endpoint теперь читает shared FX-source через `app/integrations/currency`, а не держит fetch-логику внутри UI transport

**Нормализация кодов при импорте книги**
- inline-сноски в кодах сохраняются как `footnote_refs`, но не искажают `tnved_digits`
  пример: `6301<3> -> code=6301, footnote=3`
- если в одной ячейке несколько кодов, строка разворачивается в несколько `eco_fee_map_entries`
- scientific notation из Excel разбирается по явным override-правилам
- явный мусор вроде диапазонов/дат в индекс ТН ВЭД не попадает
