# Reporting

This layer assembles final outputs for UI, Telegram and Excel.

Rules:

- `reporting/ui` builds ready-to-render UI payloads from case/work/result data;
- `reporting/telegram` builds bot-facing reply payloads and alerts;
- `reporting/excel` prepares writeback/export rows;
- `reporting/shared` keeps reusable formatting/report blocks;
- frontend and Telegram transport should not assemble screens from raw `work/*.json` directly.

Сейчас в `reporting/shared` уже лежат:

- `build_ifcg_panel()` для общего IFCG summary-packet
- `build_currency_rates_payload()` для общего FX payload поверх `integrations/currency`
