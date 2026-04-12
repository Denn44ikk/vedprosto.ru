# Template Case

Reference structure for one case folder.

This is not runtime data.
It documents how a single case should be stored after workbook intake.

Files:

- `case.json` - short normalized card used across backend;
- `source_row.json` - full source row snapshot with all columns;
- `images/` - original images for the row;
- `work/` - stage artifacts like OCR, TNVED, verification;
- `result/` - prepared outputs for UI and export.
