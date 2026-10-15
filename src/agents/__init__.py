"""The multi-agent graph. See DESIGN.md for the control-flow graph."""

from .graph import (
    DEFAULT_RECURSION_LIMIT,
    build_graph,
    retrieval_node_names,
    run_pipeline,
)
from .state import (
    AgentMode,
    CoverageVerdict,
    CritiqueVerdict,
    GraphConfig,
    TrendState,
    new_state,
)

__all__ = [
    "AgentMode", "CoverageVerdict", "CritiqueVerdict",
    "GraphConfig", "TrendState", "new_state",
    "build_graph", "run_pipeline", "retrieval_node_names",
    "DEFAULT_RECURSION_LIMIT",
]
