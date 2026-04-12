from __future__ import annotations

import os
from dataclasses import dataclass

from .agent.scenarios.ui_case_agent import UICaseAgentScenario
from .calculations.customs import CustomsCalculationService
from .calculations.eco_fee.calculator_service import EcoFeeCalculatorService
from .calculations.eco_fee.catalog_service import EcoFeeCatalogService
from .calculations.eco_fee.service import EcoFeeService
from .config import AppSettings, get_settings
from .intake.workbook.service import WorkbookIntakeService
from .intake.workbook.source_workbook_service import SourceWorkbookService
from .interfaces.tg_bot.settings.service import TgBotSettingsService
from .interfaces.ui_api.agent_cli_service import AgentCliService
from .interfaces.ui_api.chat_cli_service import ChatCliService
from .interfaces.ui_api.its_session_service import UiItsSessionService
from .interfaces.ui_api.workspace_service import WorkspaceService
from .integrations.ai.service import AIIntegrationService, build_ai_integration_service
from .integrations.currency import CurrencyService
from .integrations.ifcg import IfcgService
from .integrations.ifcg.client import IfcgClient
from .integrations.its import ITSService, TGItsClient
from .integrations.sigma import SigmaService
from .orchestrator.job_store import JobStore
from .orchestrator.pipelines.case_pipeline import CasePipelineService
from .orchestrator.workers.dispatcher import PipelineTaskDispatcher
from .orchestrator.workers.pool import PipelineWorkerPool
from .orchestrator.workers.runtime import PipelineWorkerRuntime
from .processing.ocr.service import OcrProcessingService
from .processing.semantic import SemanticService
from .processing.tnved.service import TnvedService
from .processing.tnved_vbd import TnvedVbdService
from .processing.verification import VerificationService
from .reporting.ui.analysis_placeholder_service import AnalysisPlaceholderService
from .reporting.ui.workspace.service import WorkspaceReportingService
from .storage.cases.service import CaseStorageService
from .storage.knowledge.chunking import KnowledgeChunkingService
from .storage.knowledge.catalogs import TnvedCatalogService
from .storage.knowledge.indexing import TnvedVbdIndexingService
from .storage.knowledge.vector_db import KnowledgeVectorDbService
from .storage.runtime_state.service import RuntimeStateService
from .storage.tg.db import TgDbConnection, build_tg_db_config


@dataclass
class AppContainer:
    settings: AppSettings
    db_connection: TgDbConnection | None
    ai_integration_service: AIIntegrationService
    runtime_state_service: RuntimeStateService
    job_store: JobStore
    worker_runtime: PipelineWorkerRuntime
    worker_pool: PipelineWorkerPool
    worker_dispatcher: PipelineTaskDispatcher
    eco_fee_catalog_service: EcoFeeCatalogService
    eco_fee_calculator_service: EcoFeeCalculatorService
    eco_fee_service: EcoFeeService
    currency_service: CurrencyService
    source_workbook_service: SourceWorkbookService
    ocr_processing_service: OcrProcessingService
    tnved_catalog_service: TnvedCatalogService
    knowledge_chunking_service: KnowledgeChunkingService
    knowledge_vector_db_service: KnowledgeVectorDbService
    tnved_vbd_indexing_service: TnvedVbdIndexingService
    ifcg_service: IfcgService
    its_service: ITSService | None
    sigma_service: SigmaService
    customs_service: CustomsCalculationService
    tnved_service: TnvedService
    semantic_service: SemanticService
    verification_service: VerificationService
    tnved_vbd_service: TnvedVbdService
    case_pipeline_service: CasePipelineService
    analysis_placeholder_service: AnalysisPlaceholderService
    case_storage_service: CaseStorageService
    workspace_reporting_service: WorkspaceReportingService
    case_workspace_service: WorkspaceService
    ui_its_session_service: UiItsSessionService
    agent_cli_service: AgentCliService
    chat_cli_service: ChatCliService
    workbook_intake_service: WorkbookIntakeService


def _try_build_its_service(*, settings: AppSettings, db_connection: TgDbConnection | None) -> ITSService | None:
    try:
        settings_service = TgBotSettingsService(settings, db_connection=db_connection)
        runtime_settings = settings_service.load()
        its_config = settings_service.build_its_config(runtime_settings)
        if its_config is None:
            return None
        return ITSService(
            TGItsClient(its_config),
            db_connection=db_connection,
            enabled=runtime_settings.its_enabled,
        )
    except Exception:
        return None


def build_container() -> AppContainer:
    settings = get_settings()
    db_config = build_tg_db_config()
    db_connection = TgDbConnection(db_config) if db_config is not None else None
    ai_integration_service = build_ai_integration_service(settings=settings)
    runtime_state_service = RuntimeStateService(
        state_path=settings.runtime_dir / "state.json",
    )
    job_store = JobStore()
    worker_runtime = PipelineWorkerRuntime()
    eco_fee_catalog_service = EcoFeeCatalogService(settings=settings)
    eco_fee_calculator_service = EcoFeeCalculatorService()
    eco_fee_service = EcoFeeService(
        catalog_service=eco_fee_catalog_service,
        calculator_service=eco_fee_calculator_service,
    )
    currency_service = CurrencyService()
    source_workbook_service = SourceWorkbookService(settings=settings)
    workbook_intake_service = WorkbookIntakeService(
        settings=settings,
        job_store=job_store,
        runtime_state_service=runtime_state_service,
        source_workbook_service=source_workbook_service,
    )
    ocr_processing_service = OcrProcessingService(
        ai_integration_service=ai_integration_service,
    )
    tnved_catalog_service = TnvedCatalogService()
    knowledge_chunking_service = KnowledgeChunkingService(
        chunk_size=settings.tnved_vbd_chunk_size,
        chunk_overlap=settings.tnved_vbd_chunk_overlap,
    )
    knowledge_vector_db_service = KnowledgeVectorDbService(
        embedding_backend=settings.tnved_vbd_embedding_backend,
        embedding_model=settings.tnved_vbd_embedding_model,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
    )
    tnved_vbd_indexing_service = TnvedVbdIndexingService(
        docs_dir=settings.tnved_vbd_docs_dir,
        reference_dir=settings.tnved_vbd_reference_dir,
        examples_dir=settings.tnved_vbd_examples_dir,
        index_dir=settings.tnved_vbd_index_dir,
        chunking_service=knowledge_chunking_service,
        vector_db_service=knowledge_vector_db_service,
    )
    ifcg_service = IfcgService(
        client=IfcgClient(),
        ai_service=ai_integration_service,
    )
    its_service = _try_build_its_service(settings=settings, db_connection=db_connection)
    sigma_service = SigmaService(db_connection=db_connection)
    customs_service = CustomsCalculationService()
    tnved_service = TnvedService(ai_service=ai_integration_service)
    semantic_service = SemanticService(ai_service=ai_integration_service)
    verification_service = VerificationService(ai_service=ai_integration_service)
    tnved_vbd_service = TnvedVbdService(
        indexing_service=tnved_vbd_indexing_service,
        vector_db_service=knowledge_vector_db_service,
        max_reference_hits=settings.tnved_vbd_top_k,
        max_example_hits=max(2, min(4, settings.tnved_vbd_top_k)),
    )
    case_pipeline_service = CasePipelineService(
        tnved_service=tnved_service,
        semantic_service=semantic_service,
        verification_service=verification_service,
        tnved_vbd_service=tnved_vbd_service,
        catalog_service=tnved_catalog_service,
        ifcg_service=ifcg_service,
        sigma_service=sigma_service,
        its_service=its_service,
        customs_service=customs_service,
        eco_fee_service=eco_fee_service,
    )
    analysis_placeholder_service = AnalysisPlaceholderService()
    tg_bot_settings_service = TgBotSettingsService(settings, db_connection=db_connection)
    case_storage_service = CaseStorageService(
        settings=settings,
        runtime_state_service=runtime_state_service,
    )
    workspace_reporting_service = WorkspaceReportingService(
        runtime_state_service=runtime_state_service,
        customs_service=customs_service,
        eco_fee_service=eco_fee_service,
        ocr_processing_service=ocr_processing_service,
        analysis_placeholder_service=analysis_placeholder_service,
        case_storage_service=case_storage_service,
    )
    worker_pool = PipelineWorkerPool(
        settings=settings,
        job_store=job_store,
        runtime_state_service=runtime_state_service,
        case_storage_service=case_storage_service,
        ocr_processing_service=ocr_processing_service,
        case_pipeline_service=case_pipeline_service,
        worker_runtime=worker_runtime,
    )
    worker_dispatcher = PipelineTaskDispatcher(
        settings=settings,
        job_store=job_store,
        runtime_state_service=runtime_state_service,
        worker_runtime=worker_runtime,
        worker_pool=worker_pool,
    )
    case_workspace_service = WorkspaceService(
        runtime_state_service=runtime_state_service,
        job_store=job_store,
        ocr_processing_service=ocr_processing_service,
        case_pipeline_service=case_pipeline_service,
        case_storage_service=case_storage_service,
        worker_runtime=worker_runtime,
        worker_dispatcher=worker_dispatcher,
        workspace_reporting_service=workspace_reporting_service,
    )
    ui_its_session_service = UiItsSessionService(
        settings=settings,
        settings_service=tg_bot_settings_service,
        its_service=its_service,
    )
    ui_case_agent_scenario = UICaseAgentScenario(
        settings=settings,
        ai_integration_service=ai_integration_service,
        case_workspace_service=case_workspace_service,
        tnved_catalog_service=tnved_catalog_service,
        ifcg_service=ifcg_service,
        sigma_service=sigma_service,
        its_service=its_service,
    )
    agent_cli_service = AgentCliService(ui_case_agent_scenario=ui_case_agent_scenario)
    chat_cli_service = ChatCliService(ui_case_agent_scenario=ui_case_agent_scenario)

    return AppContainer(
        settings=settings,
        db_connection=db_connection,
        ai_integration_service=ai_integration_service,
        runtime_state_service=runtime_state_service,
        job_store=job_store,
        worker_runtime=worker_runtime,
        worker_pool=worker_pool,
        worker_dispatcher=worker_dispatcher,
        eco_fee_catalog_service=eco_fee_catalog_service,
        eco_fee_calculator_service=eco_fee_calculator_service,
        eco_fee_service=eco_fee_service,
        currency_service=currency_service,
        source_workbook_service=source_workbook_service,
        ocr_processing_service=ocr_processing_service,
        tnved_catalog_service=tnved_catalog_service,
        knowledge_chunking_service=knowledge_chunking_service,
        knowledge_vector_db_service=knowledge_vector_db_service,
        tnved_vbd_indexing_service=tnved_vbd_indexing_service,
        ifcg_service=ifcg_service,
        its_service=its_service,
        sigma_service=sigma_service,
        customs_service=customs_service,
        tnved_service=tnved_service,
        semantic_service=semantic_service,
        verification_service=verification_service,
        tnved_vbd_service=tnved_vbd_service,
        case_pipeline_service=case_pipeline_service,
        analysis_placeholder_service=analysis_placeholder_service,
        case_storage_service=case_storage_service,
        workspace_reporting_service=workspace_reporting_service,
        case_workspace_service=case_workspace_service,
        ui_its_session_service=ui_its_session_service,
        agent_cli_service=agent_cli_service,
        chat_cli_service=chat_cli_service,
        workbook_intake_service=workbook_intake_service,
    )
