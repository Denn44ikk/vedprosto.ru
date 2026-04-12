from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ...dependencies import get_container
from .contracts.job import JobView
from .contracts.workbook import (
    WorkbookClearRequest,
    WorkbookClearResponse,
    WorkbookExportRequest,
    WorkbookInspectResponse,
)


router = APIRouter(prefix="/workbook", tags=["workbook"])


@router.post("/inspect", response_model=WorkbookInspectResponse)
async def inspect_workbook(
    workbook_file: UploadFile | None = File(default=None),
    workbook_path: str = Form(default=""),
    sheet_name: str = Form(default=""),
    container=Depends(get_container),
) -> WorkbookInspectResponse:
    try:
        resolved_workbook_path = workbook_path.strip()
        if workbook_file is not None and workbook_file.filename:
            saved_path = await container.workbook_intake_service.save_upload(workbook_file)
            resolved_workbook_path = str(saved_path)

        if not resolved_workbook_path:
            raise ValueError("Provide workbook_file or workbook_path.")

        payload = container.workbook_intake_service.inspect_workbook(
            workbook_path=resolved_workbook_path,
            sheet_name=sheet_name.strip() or None,
        )
        return WorkbookInspectResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/export", response_model=JobView)
def export_case_folders(request: WorkbookExportRequest, container=Depends(get_container)) -> JobView:
    try:
        payload = container.workbook_intake_service.export_case_folders(
            workbook_path=request.workbook_path,
            sheet_name=request.sheet_name,
            rows=request.rows,
            output_dir=request.output_dir,
            detect_duplicates=request.detect_duplicates,
            header_row=request.header_row,
        )
        return JobView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/clear", response_model=WorkbookClearResponse)
def clear_workbook(request: WorkbookClearRequest, container=Depends(get_container)) -> WorkbookClearResponse:
    try:
        payload = container.workbook_intake_service.clear_workbook(request.workbook_path)
        return WorkbookClearResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
