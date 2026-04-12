# App Layer

`app/` is the backend code root.

Current runtime still starts through the existing layer:

- `main.py`
- `app_factory.py`
- `integrations/`

Current structure:

- `interfaces/`
- `intake/`
- `orchestrator/`
- `processing/`
- `calculations/`
- `integrations/`
- `reporting/`
- `storage/`

Important shared-path rules:

- `interfaces/*` stay transport-only and should not own business fetch/parsing logic for external systems;
- `integrations/*` own shared clients/connectors/parsers for external sources;
- `reporting/shared` holds reusable payload builders that UI and TG can both consume;
- `calculations/*` may depend on shared integrations, but should not reimplement transport logic there.

Migration rule:

- do not break the current runtime while reshaping the code;
- keep logic in the target folders only;
- remove legacy folders after each piece is fully replaced.
