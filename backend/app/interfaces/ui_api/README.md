# UI API

`interfaces/ui_api` — это transport и coordinator layer для браузерного UI.

Что здесь должно жить:

- FastAPI routes
- request/response contracts
- тонкие adapter/coordinator-сервисы

Что здесь не должно жить:

- сборка экранного payload
- бизнес-формулы
- отдельная UI-специфичная логика по eco/customs/IFCG

Актуальные модули:

- `router.py`
- `workspace.py`
- `workspace_service.py`
- `workbook.py`
- `jobs.py`
- `eco_fee.py`
- `its_session.py`
- `agent_cli.py`
- `chat_cli.py` (legacy alias)
- `contracts/`

Важно:

- `workspace_service.py` теперь только координирует root/case/job/run-ocr/stop и отдает сборку через `reporting/ui/workspace/service.py`
- основной advisor transport идет через `agent_cli.py`; `chat_cli.py` оставлен только как alias
- основной экран экосбора читает `current_case.eco_fee` из `/api/workspace`
- отдельный `eco_fee.py` нужен только для reference/debug/currency helper endpoints
- даже `currency-rates` здесь не вычисляется напрямую: route берет shared FX snapshot из `integrations/currency`
- наружу этот FX snapshot формируется через `reporting/shared/currency.py`, чтобы тот же payload потом мог использовать и TG
