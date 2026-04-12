# Calculations

Mathematical and fee-related logic lives here.

Current intent:

- `customs/` owns duty / VAT / STP math;
- `eco_fee/` owns eco lookup, match, calc and shared runtime packet;
- live external inputs such as FX should come in through shared dependencies from `app/integrations/*`, not through UI routes.

For eco specifically:

- `app/calculations/eco_fee` is the domain layer for eco math and matching;
- `app/integrations/currency` is the shared FX source;
- `app/reporting/shared/currency.py` formats FX snapshots for transports.
