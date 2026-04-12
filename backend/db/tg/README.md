# TG Database Scripts

Порядок запуска:

1. Убедиться, что `psql` доступен в `PATH`.
2. Заполнить `TG_DB_URL` в `.env` или передать `-DatabaseUrl` в `run_all.ps1`.
3. Запустить `run_all.ps1`.

Скрипты:

- `010_schema.sql` создает таблицы TG
- `020_indexes.sql` создает индексы
- `030_seed_runtime_settings.sql` создает singleton-строку runtime settings

`session` Telegram не хранится в БД и остается файловой на диске.
