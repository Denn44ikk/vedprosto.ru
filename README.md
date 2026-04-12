# VedProsto

Standalone-репозиторий операторского UI и backend для анализа товарных строк: OCR, подбор ТН ВЭД, IFCG / Sigma / ITS enrichment, расчеты пошлин, СТП и экосбора, а также case-aware chat по текущему товару.

Production-домен проекта:

- `http://vedprosto.ru/`
- `http://www.vedprosto.ru/`
- IP fallback: `http://83.147.234.54/`

## Что внутри

- `frontend/`
  Статический интерфейс оператора на HTML/CSS/JS. Фронт остаётся тонким и читает готовый payload из backend.

- `backend/app/`
  FastAPI-приложение, orchestrator pipeline, integrations, calculations, reporting, storage и case-aware agent.

- `backend/db/`
  SQL и bootstrap-материалы для PostgreSQL слоёв TG, Sigma и knowledge storage.

- `backend/deploy/`
  Скрипты и шаблоны для выкладки backend + frontend на VPS.

- `map.md`
  Краткая карта всего репозитория.

- `backend/map.md`
  Подробная карта backend-архитектуры и data flow.

- `plan.md`
  Рабочая фиксация статуса миграции и ближайших задач.

## Принцип проекта

- UI не собирает бизнес-логику сам.
- Backend отдает готовый workspace payload через `/api/workspace`.
- Runtime-данные, загруженные таблицы, кейсы, логи, session-файлы и локальные секреты в git не хранятся.

## Локальный запуск

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8011
```

Или через wrapper:

```powershell
cd backend
.\run_backend.ps1
```

После старта открыть `http://127.0.0.1:8011`.

## Настройка

1. Скопировать `.env.example` в `.env`.
2. Заполнить AI-ключи и нужные TG / ITS / DB настройки.
3. Для deploy создать `backend/deploy/server.config.local.json` на основе `server.config.example.json`.

Файлы `.env`, `.env.*`, `server.config.local.json`, `runtime/` и `backend/runtime/` игнорируются git.

## Deploy

```powershell
cd backend
python deploy\deploy_ui.py --config deploy\server.config.local.json
```

Deploy-пакет:

- отправляет `backend/app`, `frontend`, `requirements.txt` и deploy-материалы на сервер
- поднимает или обновляет Python venv
- запускает backend через `systemd`
- обновляет Caddy-конфигурацию
- проверяет `/api/health`

## Быстрые проверки

```powershell
cd backend
python -m compileall -q app
node --check ..\frontend\assets\api.js
node --check ..\frontend\assets\render.js
node --check ..\frontend\assets\app.js
```

## Навигация по коду

1. Начать с `map.md`.
2. Затем открыть `backend/map.md`.
3. Для текущего статуса миграции смотреть `plan.md`.
