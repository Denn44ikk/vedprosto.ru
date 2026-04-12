# Sigma Database Scripts

Минимальный кэш Sigma хранится в одной таблице:

- `cache_key` - ключ вида `code:query_date`
- `payload_json` - готовый типовой payload Sigma
- `success` - можно ли переиспользовать запись
- `updated_at` - время последнего обновления

Правило использования:

1. Приходит `code + query_date`
2. Собирается `cache_key`
3. Если запись есть, `success = true` и `updated_at >= NOW() - INTERVAL '7 days'`
   результат сразу отдается из БД
4. Иначе Sigma запрашивается заново, и запись перезаписывается

Скрипты:

- `010_schema.sql` - создает минимальную таблицу кэша Sigma
- `020_indexes.sql` - создает индекс для TTL-cleanup по `updated_at`
- `030_cleanup_7_days.sql` - удаляет записи старше 7 дней
- `run_all.ps1` - запускает schema + indexes + cleanup
