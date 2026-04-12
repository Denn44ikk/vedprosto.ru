# Orchestrator

This layer owns the execution order.

- `shared_flow.py` is the common analysis pipeline
- `ui_flow.py` adds UI specifics
- `tg_flow.py` adds Telegram specifics
- `workers/*` should own generic job/task/worker runtime for both UI and TG

Business logic itself belongs in `processing/`, `integrations/`, `calculations/`, and `reporting/`.
