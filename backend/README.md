# Backend

Backend собран как общее ядро для UI и будущего TG.

Актуальный runtime-path:

- `app/interfaces/` — transport layer
- `app/intake/` — workbook intake и создание `case`
- `app/orchestrator/` — общий pipeline и worker runtime
- `app/processing/` — OCR / TNVED / semantic / verification
- `app/calculations/` — customs / STP / eco_fee
- `app/integrations/` — AI / IFCG / ITS / Sigma / Telegram
- `app/reporting/` — сборка готовых payload для UI / TG / Excel
- `app/storage/` — case storage, runtime state, knowledge catalogs, TG DB

## Что важно сейчас

- основной UI route `/api/workspace` идет через `interfaces/ui_api/workspace.py`
- `WorkspaceService` остается coordinator-слоем: root/case/jobs/run-ocr/stop
- экранный payload собирается в `reporting/ui/workspace/service.py`
- экосбор уже не строится из фронта через ручные lookup/calc-вызовы:
  UI читает `current_case.eco_fee` из общего workspace payload
- primary case-assistant path для UI теперь идет через `/api/agent-cli/*`
- `/api/chat-cli/*` оставлен только как legacy alias/shim
- во время pipeline UI-карточка case уходит в blur и показывает progress overlay,
  который строится по `work_status` и `stage_statuses` из `/api/workspace`
- inspect/export workbook валидируют таблицу одинаково:
  merged cells запрещены, `Наименование` обязательно и ищется без учета регистра,
  `Доп информация` опциональна, image-ошибки схлопываются в компактные списки строк
- общий pipeline теперь честно пишет `timeout/error` на внешних стадиях
  `IFCG / ITS / Sigma`, а не оставляет вечный `pending`
- если `Sigma` не вернула `VAT`, для customs/STP временно используется fallback `НДС=22%`
- минимальный timeout `ITS` в pipeline поднят до `60` секунд, чтобы уменьшить ложные timeout'ы
- live-path `Sigma` временно упрощен ради стабильности:
  shared async cache/worker path выведен из критического runtime, чтобы убрать `different loop`

## Экосбор

Экосбор разделен на два слоя:

- `app/storage/knowledge/catalogs/eco_fee`
  парсер книги `Расчет экосбора.xlsx`, нормализация кодов, sync в Postgres
- `app/calculations/eco_fee`
  lookup, матчинг, packet `eco.by_code -> years -> matches`

Дополнительно UI-side helper endpoint:

- `GET /api/eco-fee/currency-rates`
  актуальные `USD / EUR` от ЦБ РФ для подсказок оператора

Источник этих курсов теперь общий:

- `app/integrations/currency`
- shared formatting/helper слой: `app/reporting/shared/currency.py`

То есть UI transport только пробрасывает shared FX snapshot наружу, а не владеет логикой загрузки курсов сам.

Важно по legacy eco routes:

- `/api/eco-fee/lookup`
- `/api/eco-fee/calculate`

Они больше не являются основным UI-path.
Главный экран уже работает через `current_case.eco_fee` из `/api/workspace`.
Эти маршруты пока оставлены как reference/debug entrypoints и как кандидаты на удаление после проверки внешних consumers.

## UI API

В `app/interfaces/ui_api/` сейчас активны:

- `workspace.py`
- `workbook.py`
- `jobs.py`
- `eco_fee.py`
- `its_session.py`
- `agent_cli.py`
- `chat_cli.py` - legacy alias на `agent_cli`
- `health.py`

Контракты живут в `app/interfaces/ui_api/contracts/`.

## Запуск

Основной старт для локальной работы:

```powershell
cd backend
.\run_backend.ps1
```

Скрипт берет интерпретатор в таком порядке:

- `..\.venv\Scripts\python.exe`
- `C:\Python314\python.exe`

После старта UI доступен по:

- `http://127.0.0.1:8011`
