# Product Deploy

Эта папка хранит product-level deploy для сервера.

Что деплоим сейчас:

- сайт для UI;
- backend через `systemd` на внутреннем `127.0.0.1:8011`;
- Caddy как внешний reverse proxy на `80/443`;
- persistent `runtime` volume на сервере.
- IP-фоллбек остается на `http://83.147.234.54`; `vedprosto.ru` сейчас держим на HTTP, а HTTPS включается через Caddy после подтверждения доступности ACME-проверок на 80/443.
- ITS runtime как часть UI, если в `server.config.local.json` включен `TG_ITS_ENABLED` и локально есть `backend/runtime/tg/...`.
- runtime-переключатель ITS хранится в `TG_RUNTIME_SETTINGS_PATH`, чтобы аварийное выключение бота переживало рестарт сервиса.

Что пока не деплоим:

- отдельный Telegram bot worker;
- отдельные вспомогательные сервисы за пределами UI-сайта.

Идея текущего rollout:

1. Локальный launcher подключается к серверу по SSH.
2. Ставит Caddy, если его нет.
3. Загружает app bundle:
   - `backend/app`
   - `frontend`
   - корневой `requirements.txt`
  - опционально `backend/runtime/tg/its/tg_config.json`
  - опционально `backend/runtime/tg/sessions/tg_its.session`
  - persistent `backend/runtime/tg/its/runtime_settings.json` остается на сервере и не затирается деплоем
4. Загружает remote stack:
   - `Dockerfile.backend`
   - `docker-compose.yml`
   - `Caddyfile` для домена/HTTPS
5. Генерирует remote `.env`.
6. Поднимает backend через `systemd`.
7. Обновляет `/etc/caddy/Caddyfile` и перезагружает Caddy.
8. Проверяет `GET /api/health`.

Структура:

- `server.config.example.json` — шаблон конфига.
- `server.config.local.json` — локальный секретный конфиг, в git не хранится.
- `deploy_ui.py` — основной deploy launcher.
- `deploy_ui.ps1` — Windows-обертка для запуска.
- `deploy_requirements.txt` — зависимости launcher'а.
- `remote/ui_stack/*` — remote stack заготовки для сайта.

Быстрый запуск:

```powershell
cd backend\deploy
.\deploy_ui.ps1
```

После первой рабочей версии можно будет расширить эту же папку:

- `ui + tg` compose profile;
- backup/cleanup сценарии.
