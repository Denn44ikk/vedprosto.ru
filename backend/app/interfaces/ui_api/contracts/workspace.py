from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceRootView(BaseModel):
    root_path: str
    label: str
    is_active: bool


class WorkspaceCaseView(BaseModel):
    case_id: str
    row_number: int
    row_span: str
    title: str
    image_count: int
    review_status: str
    prefetch_status: str
    ocr_status: str
    has_ai_result: bool
    is_current: bool


class WorkspaceImageView(BaseModel):
    name: str
    url: str


class WorkspaceSummaryView(BaseModel):
    tnved: str
    posh: str
    eco: str
    its: str
    its_value: float | None
    nds: str
    stp: str
    stp_value: float | None
    declaration_description: str
    label_text: str


class WorkspaceCodeOptionView(BaseModel):
    option_key: str
    code: str
    confidence_percent: int
    level: str
    branch_type: str
    title: str
    why_alive: str
    posh: str
    eco: str
    its: str
    its_value: float | None
    nds: str
    stp: str
    stp_value: float | None
    priority: int


class WorkspaceSupportSectionView(BaseModel):
    title: str
    value: str


class WorkspaceIfcgGroupView(BaseModel):
    code: str
    record_count: int
    share_percent: int


class WorkspaceIfcgFocusedQueryView(BaseModel):
    group_filter: str
    codes: list[WorkspaceIfcgGroupView]


class WorkspaceIfcgQueryView(BaseModel):
    index: int
    text: str
    url: str
    groups: list[WorkspaceIfcgGroupView]
    focused: list[WorkspaceIfcgFocusedQueryView]


class WorkspaceIfcgTopCodeView(BaseModel):
    code: str
    support_level: str
    signal_type: str
    records: int
    share_percent: int
    why: str
    its_value: float | None = None
    its_status: str = ""
    its_date_text: str = ""


class WorkspaceIfcgInlineCodeView(BaseModel):
    code: str
    records: int
    share_percent: int
    support_level: str
    signal_type: str
    query_hits: int
    short_line: str
    verify_line: str = ""


class WorkspaceIfcgPanelView(BaseModel):
    status: str
    summary: str
    verify_summary: str
    selected_code: str
    selected_summary: WorkspaceIfcgInlineCodeView | None = None
    candidate_summaries: list[WorkspaceIfcgInlineCodeView] = Field(default_factory=list)
    review_headline: str = ""
    strongest_code: str = ""
    query_count: int
    queries: list[WorkspaceIfcgQueryView]
    top_codes: list[WorkspaceIfcgTopCodeView]
    hidden_queries: int = 0
    rerun_recommended: bool = False
    dangerous_signal: bool = False


class WorkspaceAnalysisSectionView(BaseModel):
    title: str
    value: str


class WorkspaceAnalysisHighlightView(BaseModel):
    label: str
    value: str
    tone: str = "neutral"


class WorkspaceQuestionView(BaseModel):
    id: str
    question: str
    why: str = ""
    source_stage: str = ""
    priority: int = 0
    related_codes: list[str] = Field(default_factory=list)
    status: str = "open"
    answer: str = ""


class WorkspaceSourceFieldView(BaseModel):
    label: str
    value: str


class WorkspaceSourceTableRowView(BaseModel):
    label: str
    values: list[str]


class WorkspaceSourceTableView(BaseModel):
    status: str
    workbook_name: str
    workbook_path: str
    sheet_name: str
    row_labels: list[str]
    note: str
    fields: list[WorkspaceSourceTableRowView]


class WorkspaceEcoFeeFootnoteView(BaseModel):
    ref: str
    marker: str
    text: str


class WorkspaceEcoFeeDbEntryView(BaseModel):
    entry_key: str
    source_row: int
    row_name: str
    okpd2: str
    tnved_raw: str
    tnved_digits: str
    tnved_name: str
    eco_group_code: str
    eco_group_name: str
    footnotes: list[WorkspaceEcoFeeFootnoteView] = Field(default_factory=list)


class WorkspaceEcoFeeMatchView(BaseModel):

    selection_key: str
    eco_group_code: str
    eco_group_name: str
    match_kind: str
    matched_digits_length: int
    source_rows: list[int]
    matched_codes: list[str]
    examples: list[str]
    db_entries: list[WorkspaceEcoFeeDbEntryView] = Field(default_factory=list)
    footnotes: list[WorkspaceEcoFeeFootnoteView] = Field(default_factory=list)
    rate_rub_per_ton: float | None
    rate_rub_per_kg: float | None
    complexity_coeff: float | None
    utilization_norm: float | None
    preview: str
    surcharge_usd_per_kg: float | None = None
    short_text: str = ""
    names_text: str = ""


class WorkspaceEcoFeeYearView(BaseModel):
    year: int
    status: str
    note: str
    preview: str
    usd_rate: float | None
    packaging_norm: float | None
    matches_count: int
    short_text: str
    names_text: str
    best_match: WorkspaceEcoFeeMatchView | None = None
    matches: list[WorkspaceEcoFeeMatchView] = Field(default_factory=list)


class WorkspaceEcoFeeCodeView(BaseModel):
    code: str
    code_digits: str
    default_year: int
    selected_year: int
    supported_years: list[int]
    status: str
    note: str
    short_text: str
    names_text: str
    years: list[WorkspaceEcoFeeYearView] = Field(default_factory=list)


class WorkspaceEcoFeeView(BaseModel):
    default_year: int
    supported_years: list[int]
    by_code: list[WorkspaceEcoFeeCodeView] = Field(default_factory=list)


class WorkspaceTnvedVbdHitView(BaseModel):
    chunk_id: str
    source_path: str
    relative_path: str
    source_kind: str
    document_type: str
    section_context: str = ""
    text: str = ""
    score: float = 0.0
    mentioned_codes: list[str] = Field(default_factory=list)


class WorkspaceTnvedVbdView(BaseModel):
    status: str
    verification_status: str = "pending"
    selected_code: str = ""
    summary: str = ""
    note: str = ""
    product_facts: list[str] = Field(default_factory=list)
    reference_hits: list[WorkspaceTnvedVbdHitView] = Field(default_factory=list)
    example_hits: list[WorkspaceTnvedVbdHitView] = Field(default_factory=list)
    alternative_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    index_status: str = ""


class WorkspaceCaseDetailView(BaseModel):
    case_id: str
    row_number: int
    row_span: str
    source_rows: list[int]
    title_cn: str
    title_ru: str
    text_cn: str
    text_ru: str
    ocr_text: str
    image_description: str
    images: list[WorkspaceImageView]
    summary: WorkspaceSummaryView
    code_options: list[WorkspaceCodeOptionView]
    analysis_sections: list[WorkspaceAnalysisSectionView]
    analysis_highlights: list[WorkspaceAnalysisHighlightView]
    questions: list[str] = Field(default_factory=list)
    question_items: list[WorkspaceQuestionView] = Field(default_factory=list)
    long_report: str
    source_fields: list[WorkspaceSourceFieldView]
    source_table: WorkspaceSourceTableView
    support_sections: list[WorkspaceSupportSectionView]
    ifcg_panel: WorkspaceIfcgPanelView | None = None
    stage_statuses: dict[str, str] = Field(default_factory=dict)
    eco_fee: WorkspaceEcoFeeView | None
    tnved_vbd: WorkspaceTnvedVbdView | None = None
    background_status: str
    ocr_status: str
    has_ai_result: bool
    work_status: str
    work_stage: str


class WorkspaceCountersView(BaseModel):
    total: int
    pending: int
    saved: int
    skipped: int


class WorkspaceView(BaseModel):
    roots: list[WorkspaceRootView]
    active_root_path: str
    current_case_id: str
    counters: WorkspaceCountersView
    cases: list[WorkspaceCaseView]
    current_case: WorkspaceCaseDetailView | None


class WorkspaceRootSelectRequest(BaseModel):
    root_path: str


class WorkspaceRootDeleteRequest(BaseModel):
    root_path: str


class WorkspaceCurrentCaseRequest(BaseModel):
    case_id: str


class WorkspacePrefetchRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=20)


class WorkspaceRunOcrRequest(BaseModel):
    case_id: str = ""
