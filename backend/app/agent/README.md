Agent layer поверх `integrations/ai` и внутренних Python-модулей.

Что здесь лежит:

- `core/`
  Общая механика agent-runtime:
  transcript, context packet, attachments, engine, session state.

- `tools/`
  Python tool-wrappers над case/runtime и внешними модулями:
  `IFCG`, `Sigma`, `ITS`, `TNVED catalog`, web search.

- `scenarios/`
  Agent-сценарии под разные каналы:
  UI case agent, terminal case agent, future TG case agent.

- `cli_case_agent.py`
  Terminal entrypoint для свободного case-aware агента.

Принцип:

- `chat` больше не является primary layer для case advisor.
- `agent` читает case, знает ваши Python-модули и может подмешивать web/tool digests.
- primary runtime работает асинхронно:
  `ITS`, `Sigma`, `IFCG` и модель могут вызываться в одном agent-cycle.
- transport-слои UI/TG/terminal должны вызывать `agent/scenarios`, а не собирать prompt вручную.
- UI primary transport идет через `/api/agent-cli/*`;
  `/api/chat-cli/*` оставлен только как legacy alias.

Текущее состояние runtime:

- `agent` читает `case.json`, `source_row.json`, `work/*.json`, `result/*.json`, `work/questions.json`
- изображения case прикладываются через общий attachments layer
- `IFCG`, `ITS`, `Sigma`, `TNVED catalog` и web research доступны агенту через `tools/`
- `chat/*` больше не является source of truth и оставлен только как compatibility shim
