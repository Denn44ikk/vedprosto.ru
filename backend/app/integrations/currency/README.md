# Currency Integration

Общий backend-модуль для курсов валют.

Сейчас источник один:

- ЦБ РФ daily XML

Назначение:

- один shared FX-source для UI, TG и расчетных модулей
- transport-слои не должны сами ходить за курсами
- `calculations/*` могут использовать этот модуль как dependency, если нужен live FX

Текущий сервис:

- `service.py`
  - `CurrencyService.get_cbr_daily_rates()`

Текущая shared-модель:

- `CurrencyRatesSnapshot`
- `CurrencyRate`

Для форматирования наружу используется:

- `app/reporting/shared/currency.py`
