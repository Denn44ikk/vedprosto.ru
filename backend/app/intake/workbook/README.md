# Workbook Intake

`00` now lives here by meaning, not as a numbered module.

Responsibilities:

- save uploaded workbook
- inspect workbook structure
- choose sheet and rows
- export case folders
- persist workbook metadata for later workspace use

Implementation note:

- case export now runs inside this package via `exporter.py`;
- external `00_module_0/export_case_folders.py` is no longer used by backend runtime.
