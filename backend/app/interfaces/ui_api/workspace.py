from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ...dependencies import get_container
from .contracts.workspace import (
    WorkspaceCurrentCaseRequest,
    WorkspacePrefetchRequest,
    WorkspaceRootDeleteRequest,
    WorkspaceRootSelectRequest,
    WorkspaceRunOcrRequest,
    WorkspaceView,
)


router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceView)
def get_workspace(container=Depends(get_container)) -> WorkspaceView:
    return WorkspaceView(**container.case_workspace_service.get_workspace())


@router.post("/root", response_model=WorkspaceView)
def set_workspace_root(request: WorkspaceRootSelectRequest, container=Depends(get_container)) -> WorkspaceView:
    try:
        payload = container.case_workspace_service.set_active_root(request.root_path)
        return WorkspaceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/delete-root", response_model=WorkspaceView)
def delete_workspace_root(request: WorkspaceRootDeleteRequest, container=Depends(get_container)) -> WorkspaceView:
    try:
        payload = container.case_workspace_service.delete_root(request.root_path)
        return WorkspaceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/current-case", response_model=WorkspaceView)
def set_current_case(request: WorkspaceCurrentCaseRequest, container=Depends(get_container)) -> WorkspaceView:
    try:
        payload = container.case_workspace_service.set_current_case(request.case_id)
        return WorkspaceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/save-excel", response_model=WorkspaceView)
def save_to_excel(container=Depends(get_container)) -> WorkspaceView:
    try:
        payload = container.case_workspace_service.save_to_excel()
        return WorkspaceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/skip", response_model=WorkspaceView)
def skip_current_case(container=Depends(get_container)) -> WorkspaceView:
    try:
        payload = container.case_workspace_service.skip_current_case()
        return WorkspaceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/prefetch", response_model=WorkspaceView)
def prefetch_next_cases(request: WorkspacePrefetchRequest, container=Depends(get_container)) -> WorkspaceView:
    try:
        payload = container.case_workspace_service.prefetch_next_cases(count=request.count)
        return WorkspaceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run-ocr", response_model=WorkspaceView)
def run_case_ocr(request: WorkspaceRunOcrRequest, container=Depends(get_container)) -> WorkspaceView:
    try:
        payload = container.case_workspace_service.run_ocr(request.case_id)
        return WorkspaceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stop-ocr", response_model=WorkspaceView)
def stop_case_ocr(container=Depends(get_container)) -> WorkspaceView:
    try:
        payload = container.case_workspace_service.stop_ocr()
        return WorkspaceView(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cases/{case_id}/images/{image_name}")
def get_case_image(case_id: str, image_name: str, container=Depends(get_container)) -> FileResponse:
    try:
        image_path = container.case_workspace_service.resolve_case_image_path(case_id, image_name)
        return FileResponse(image_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
