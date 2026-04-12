"""IFCG integration layer."""

from .client import IfcgClient
from .models import (
    IfcgAnalysisResult,
    IfcgCodeSummary,
    IfcgDecisionStatus,
    IfcgDiscoveryInput,
    IfcgDiscoveryOutput,
    IfcgInput,
    IfcgOutput,
    IfcgQuery,
    IfcgQueryPlan,
    IfcgSearchResult,
)
from .service import IfcgService

__all__ = [
    "IfcgAnalysisResult",
    "IfcgClient",
    "IfcgCodeSummary",
    "IfcgDecisionStatus",
    "IfcgDiscoveryInput",
    "IfcgDiscoveryOutput",
    "IfcgInput",
    "IfcgOutput",
    "IfcgQuery",
    "IfcgQueryPlan",
    "IfcgSearchResult",
    "IfcgService",
]
