Legacy compatibility layer поверх `integrations/ai`.
Primary layer для case advisor переехал в `app/agent`.

Что здесь лежит:

- `core/`
  Legacy shim на `app/agent/core`.
  Реальный runtime теперь живет в `agent/core`, а `chat/core` оставлен только ради обратной совместимости импортов.

- `scenarios/`
  Legacy aliases и совместимость для старых transport/import путей:
  UI case chat, terminal case chat, Telegram case chat, operator chat.
  Primary runtime для case advisor теперь живет в `app/agent/scenarios`.

- `cli_case_chat.py`
  Terminal entrypoint для case-aware chat без UI и API.
  Он читает весь `case`:
  `case.json`, `source_row.json`, `work/*.json`, `result/*.json`, transcript и изображения.

Legacy запуск:

```bash
python -m app.chat.cli_case_chat --case-dir "runtime/uploads/<root>/<case_id>"
```

Одноразовый вопрос:

```bash
python -m app.chat.cli_case_chat --case-dir "runtime/uploads/<root>/<case_id>" --message "Какой сейчас итоговый код и почему?"
```

Правило разделения:

- `integrations/ai` не знает про UI, Telegram, кейсы и бизнес-логику.
- `agent/core` — основной низкоуровневый runtime-слой.
- `chat/core` — только compatibility shim.
- `chat/scenarios` не должен быть source of truth для новой архитектуры.
- `app/agent/scenarios` использует тот же низкоуровневый runtime, но выступает как primary case-aware agent layer.
- `chat/research/web_search_service.py` и `chat/scenarios/*` оставлены ради совместимости и могут истончаться до alias/re-export.
- `interfaces/ui_api` и `interfaces/tg_bot` остаются transport/adapters.
