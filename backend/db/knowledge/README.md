# Knowledge DB

Сюда вынесены SQL-скрипты для knowledge-таблиц backend.

Сейчас здесь лежит схема для:

- `tnved_catalog`
- `tnved_catalog_meta`

Каталог ТН ВЭД обновляется модулем:

- `app/storage/knowledge/catalogs/tnved_catalog/service.py`
- `app/storage/knowledge/catalogs/tnved_catalog/updater.py`

Логика такая:

- каталог сначала обновляется как file-backed snapshot (`catalog.json` + `state.json`);
- затем этот snapshot может быть полностью залит в PostgreSQL;
- таблица `tnved_catalog_meta` хранит метаданные последнего активного импорта.
