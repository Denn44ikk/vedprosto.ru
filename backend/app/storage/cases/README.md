# Cases Storage

Shared case storage for workbook/table workflows.

Here we keep:

- discovered case roots;
- case folders and artifacts;
- access helpers for `case.json`, `work/*.json` and images;
- a reference template in `template_case/` that defines the expected structure.

Typical split inside one case:

- `case.json` - normalized short card of the case;
- `source_row.json` - full snapshot of the source table row;
- `images/` - source images for the row;
- `work/` - artifacts of pipeline stages;
- `result/` - channel-neutral pipeline result plus derived outputs for UI/export.

Current contract:

- `work/ocr.json` - OCR output;
- `work/tnved.json` - TNVED stage output with candidates and trace;
- `work/verification.json` - semantic/verification status snapshot;
- `work/enrichment.json` - enrichment layer state: IFCG discovery/verification, ITS, Sigma;
- `work/calculations.json` - calculations layer state: customs, STP, eco fee;
- `work/questions.json` - top clarification questions plus future operator answers;
- `result/pipeline_result.json` - main source of truth for cross-channel integration;
- `result/ui_response.json` - UI-oriented projection;
- `result/export.json` - export-oriented projection.
