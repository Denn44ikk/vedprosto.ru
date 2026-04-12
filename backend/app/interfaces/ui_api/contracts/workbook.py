from __future__ import annotations

from pydantic import BaseModel, Field


class WorkbookPreviewRow(BaseModel):
    row_number: int
    display_name: str
    secondary_text: str
    image_count: int
    has_images: bool


class WorkbookInspectResponse(BaseModel):
    workbook_path: str
    sheet_names: list[str]
    selected_sheet: str
    headers: list[str]
    required_headers: list[str]
    optional_headers: list[str]
    missing_required_headers: list[str]
    matched_required_headers: dict[str, str] = Field(default_factory=dict)
    has_merged_cells: bool = False
    merged_ranges: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    is_workbook_compatible: bool
    total_data_rows: int
    preview_row_limit: int
    preview_truncated: bool
    preview_rows: list[WorkbookPreviewRow]


class WorkbookExportRequest(BaseModel):
    workbook_path: str
    sheet_name: str
    rows: str = Field(default="2-20")
    output_dir: str | None = None
    detect_duplicates: bool = True
    header_row: int = 1


class WorkbookClearRequest(BaseModel):
    workbook_path: str = ""


class WorkbookClearResponse(BaseModel):
    cleared: bool
    removed_file: bool
    workbook_path: str
