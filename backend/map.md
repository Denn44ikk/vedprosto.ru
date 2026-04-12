# Backend Map

Эта карта описывает backend как отдельное ядро репозитория `VedProsto`. Здесь собраны transport-слои для UI и Telegram, единый pipeline анализа товара, case-aware agent, интеграции с внешними сервисами и file/database storage.

## Верхний уровень

```text
backend/
├── app/                # Код приложения
├── db/                 # SQL и bootstrap для PostgreSQL
├── deploy/             # Скрипты и шаблоны VPS deploy
├── runtime/            # Локальные runtime-данные, не коммитятся
├── README.md
├── map.md
└── run_backend.ps1
```

## App Layout

```text
backend/app/
├── app_factory.py      # Сборка FastAPI-приложения
├── config.py           # Чтение .env и путей runtime
├── container.py        # DI-контейнер и wiring сервисов
├── dependencies.py     # Зависимости для transport-слоёв
├── main.py             # HTTP entrypoint
├── tg_main.py          # Отдельный entrypoint для TG runtime
│
├── interfaces/         # Transport adapters
├── intake/             # Вход из Excel и создание cases
├── orchestrator/       # Общая последовательность обработки
├── processing/         # OCR, TNVED, semantic, verification
├── calculations/       # Customs, STP, eco fee
├── integrations/       # AI, IFCG, ITS, Sigma, Telegram, currency
├── agent/              # Primary case-aware agent runtime
├── chat/               # Compatibility shim поверх agent
├── reporting/          # Готовые payload для UI, TG и Excel
├── security/           # Access gate и общие ограничения
└── storage/            # File storage, knowledge и TG DB layer
```

## Слои и ответственность

### `interfaces/`

- `ui_api/`
  HTTP API для операторского UI.
  Основные маршруты:
  `workspace`, `workbook`, `jobs`, `eco_fee`, `its_session`, `agent_cli`, `chat_cli`, `auth`, `health`.

- `tg_bot/`
  Telegram transport: bot lifecycle, routing, handlers, queue и settings-controller.

### `intake/workbook/`

Табличный вход в систему:

- inspect workbook
- выбор листа
- выбор диапазона строк
- создание `case-root`
- экспорт результата обратно в Excel

### `orchestrator/`

Координационный слой, который не дублирует бизнес-логику модулей, а управляет порядком запуска:

- `shared_flow.py`
  Общий pipeline анализа товара

- `ui_flow.py`
  Общий pipeline + поведение, нужное UI

- `tg_flow.py`
  Общий pipeline + поведение, нужное TG

- `pipelines/case_pipeline.py`
  Сборка stage-результатов в единый case result

- `workers/`
  Runtime задач: pool, dispatcher, limits, models и lifecycle управления

### `processing/`

Доменные этапы анализа товара:

- `ocr/`
  OCR и извлечение структуры из изображений

- `tnved/`
  Подбор кода, критерии, кандидаты, вопросы для уточнения

- `semantic/`
  Смысловые проверки и web-hint логика

- `verification/`
  Проверка и repair итогового кода

### `calculations/`

- `customs/`
  Пошлины, НДС и effective duty math

- `eco_fee/`
  Lookup и расчет экосбора поверх knowledge catalog

- `stp/`
  Transitional shim, пока STP folded into customs service

### `integrations/`

- `ai/`
  Общий AI gateway, профили, провайдеры и CLI runtime

- `ifcg/`
  Client, parser, planner, ranking, judge и unified output

- `its/`
  ITS client/service/models

- `sigma/`
  Sigma connector, parser, price-view и service layer

- `currency/`
  Общий источник валютных курсов для UI helper и shared reporting

- `telegram/`
  Telegram-specific transport clients

### `agent/` и `chat/`

- `agent/`
  Source of truth для case-aware assistant:
  `core`, `tools`, `research`, `scenarios`

- `chat/`
  Совместимость с legacy import path поверх `agent`

### `reporting/`

- `ui/`
  Собирает экранный payload для `/api/workspace`

- `telegram/`
  Форматирует ответ для TG

- `excel/`
  Результат для записи обратно в workbook

- `shared/`
  Общие куски форматирования и summary

### `storage/`

- `cases/`
  File-backed case storage для workbook/UI сценария

- `runtime_state/`
  Локальное файловое состояние backend

- `tg/db/`
  PostgreSQL repositories и operational модели TG

- `knowledge/`
  Каталоги и справочники, которые читает pipeline

## Source Of Truth по каналам

- UI case:
  `storage/cases/<root>/<case>/case.json`
  `source_row.json`
  `work/*.json`
  `result/*.json`

- TG case:
  `storage/tg/db/*`
  `tg_messages`
  `tg_analysis_runs`
  `tg_analysis_results`
  `service_cache_*`

Один и тот же модуль должен работать с нормализованным `case context`, а не с прямой привязкой к папке или Telegram message.

## Основные data flow

### UI path

`workbook -> storage/cases -> orchestrator/pipelines/case_pipeline -> reporting/ui/workspace -> frontend`

### TG path

`telegram message -> storage/tg/db -> orchestrator/tg_flow -> reporting/telegram -> Telegram reply`

### Agent path

`workspace_service -> agent/scenarios/ui_case_agent -> agent/core + agent/tools -> integrations/ai`

### Eco fee path

`knowledge/catalogs/eco_fee -> calculations/eco_fee -> reporting/ui/workspace -> current_case.eco_fee`

## Knowledge и справочники

- `storage/knowledge/catalogs/eco_fee/`
  Хранит книгу `Расчет экосбора.xlsx` и код обновления каталога.

- `storage/knowledge/catalogs/tnved_catalog/`
  Хранит committed snapshot `catalog.json` и `state.json`.
  Временные `downloads/` и `backups/` считаются generated artifacts и в git не нужны.

## Runtime policy

`backend/runtime/` не является частью исходников. Там живут:

- активный workspace state
- загруженные Excel
- созданные case-root
- session-файлы
- runtime-логи

Эти данные локальные и в репозиторий не публикуются.

## PostgreSQL слои

### `db/tg/`

- schema для TG operational data
- indexes
- seed runtime settings
- `run_all.ps1`

### `db/sigma/`

- cache schema для Sigma
- indexes
- cleanup scripts

### `db/knowledge/`

- knowledge-таблицы под каталоги и справочники

## Текущие рабочие договоренности

- UI не строит экран из сырых `work/*.json`, а получает уже собранный payload.
- Внешние долгие стадии должны давать честные `timeout` и `error`, а не вечный `pending`.
- Agent route для UI живет в `interfaces/ui_api/agent_cli.py`.
- `chat_cli` оставлен как compatibility alias на тот же runtime.
- Workbook inspect и export должны валидировать таблицу одинаково.
