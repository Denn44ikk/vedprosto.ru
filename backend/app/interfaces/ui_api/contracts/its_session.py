from __future__ import annotations

from pydantic import BaseModel


class ItsSessionStatusView(BaseModel):
    its_enabled: bool
    runtime_status: str
    its_bot_username: str | None
    its_session_path: str
    session_file_exists: bool
    tg_api_ready: bool
    worker_running: bool
    startup_error: str | None
    pending_login: bool
    pending_step: str
    suggested_test_code: str = ""
    note: str = ""


class ItsSessionPhoneRequest(BaseModel):
    phone: str


class ItsSessionCodeRequest(BaseModel):
    code: str


class ItsSessionPasswordRequest(BaseModel):
    password: str


class ItsSessionTestQueryRequest(BaseModel):
    code: str = ""


class ItsSessionToggleRequest(BaseModel):
    enabled: bool


class ItsAccessCheckView(BaseModel):
    ok: bool
    status: str
    message: str


class ItsParsedReplyView(BaseModel):
    variant: int | None
    its: float | None
    its_scob: float | None
    date: str | None


class ItsTestQueryView(BaseModel):
    code: str
    status: str
    its_value: float | None
    its_bracket_value: float | None
    reply_variant: int | None
    date_text: str | None
    raw_reply: str
    error_text: str | None
    reply_code_match_status: str
    reply_code_candidates: list[str]
    parsed_reply: ItsParsedReplyView


class ItsSessionDiagnosticView(BaseModel):
    status: ItsSessionStatusView
    access_check: ItsAccessCheckView | None = None
    test_query: ItsTestQueryView | None = None
