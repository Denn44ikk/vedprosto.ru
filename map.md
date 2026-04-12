# VedProsto Repo Map

Этот репозиторий содержит standalone-версию `agent_ui`: операторский web-интерфейс и backend для анализа товарных строк, OCR, подбора ТН ВЭД, обогащения через IFCG / Sigma / ITS и расчета пошлин, СТП и экосбора.

## Корень репозитория

```text
.
├── frontend/          # Статический UI: HTML, CSS, JS
├── backend/           # FastAPI backend, pipeline, integrations, deploy и SQL
├── .env.example       # Пример локальной конфигурации
├── .gitignore         # Исключения для runtime, секретов и кэшей
├── README.md          # Быстрый старт и общее описание
├── map.md             # Краткая карта репозитория
├── plan.md            # Рабочий план и журнал миграции
└── requirements.txt   # Python-зависимости для backend
```

## Что где лежит

- `frontend/`
  Тонкий операторский интерфейс. Рисует экран, хранит локальный UI-state и читает готовый payload из backend.

- `backend/app/`
  Основной код приложения: transport-слои, pipeline, интеграции, расчетные сервисы, storage и reporting.

- `backend/db/`
  SQL-скрипты для PostgreSQL: TG operational schema, Sigma cache и knowledge-таблицы.

- `backend/deploy/`
  Скрипты и шаблоны one-click deploy на VPS.

- `backend/map.md`
  Подробная карта backend-архитектуры и основных data flow.

## Главные data flow

- UI path:
  `workbook -> storage/cases -> orchestrator/pipeline -> reporting/ui -> frontend`

- TG path:
  `telegram message -> storage/tg/db -> orchestrator/tg_flow -> reporting/telegram`

- Agent path:
  `case runtime -> agent/core + agent/tools -> AI provider -> UI/TG adapter`

- Eco fee path:
  `eco_fee workbook -> knowledge catalog -> calculations/eco_fee -> current_case.eco_fee`

## Что коммитим

- исходный код `frontend/` и `backend/app/`
- SQL и deploy-материалы
- `.env.example`
- committed knowledge snapshots, которые нужны приложению из коробки

## Что не коммитим

- `.env`, локальные `.local`-файлы и `server.config.local.json`
- `runtime/`, `backend/runtime/`, загруженные Excel, кейсы, логи и сессии
- `__pycache__`, build-артефакты и временные каталоги обновления справочников

## Откуда начинать чтение

1. `README.md` — что это за проект и как его запустить.
2. `backend/map.md` — как backend разложен по слоям.
3. `plan.md` — текущий статус миграции и ближайшие шаги.
