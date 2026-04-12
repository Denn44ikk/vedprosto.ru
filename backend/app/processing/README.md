# Processing

Здесь живут общие stage-модули анализа товара.

Главный принцип:

- каждый stage имеет типовой input/output;
- UI и TG не должны собирать внутреннюю логику сами;
- UI и TG вызывают один и тот же stage по одному правилу;
- stages можно вызывать по отдельности или собирать в общий pipeline через orchestrator.

Текущие stages:

- `ocr/`
  Общий OCR и нормализация входного текста/изображений.

- `tnved/`
  Первичный подбор кода ТН ВЭД.
  Здесь живут:
  `models`, `prompts`, `parsing`, `criteria`, `compaction`, `service`.
  Вход уже умеет принимать мягкий `ifcg_discovery` как дополнительный evidence.

- `semantic/`
  Смысловая проверка выбранного кода и кандидатного пула.
  Это отдельный stage, а не часть UI/TG.

- `verification/`
  Формальная проверка кода, candidate pool, repair и финальный статус.

Типовая цепочка:

- `OCR/context -> TNVED assembly -> Semantic guard -> Verification/repair -> unified result`

Важно:

- `tnved` отвечает за гипотезу и candidate pool;
- `semantic` отвечает за смысловую состоятельность гипотезы;
- `verification` отвечает за нормализацию, catalog-check и repair;
- `IFCG` может использоваться и как поздняя верификация, и как ранний evidence-слой для `tnved`.
