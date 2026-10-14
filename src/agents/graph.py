"""LangGraph wiring of the design note's agent graph.

    CriteriaAgent
          |
          v
    RetrievalDispatch
          |
          v
    Retrieval_0 .. Retrieval_N        (several cooperating agents, in parallel)
          |
          v
    RetrievalMerge
          |
          v
    CoverageAgent --(insufficient, cycle 1)--> RetrievalDispatch
          |
          | sufficient
          v
    AnalysisAgent <--(complaint, cycle 2)-- CritiqueAgent
          |                                      ^
          +--------------------------------------+
                                                 | approved
                                                 v
                                          AggregatorAgent --> END

Both back-edges are real LangGraph conditional edges rather than re-entrant
function calls, so the cycles exist in the compiled graph and can be rendered.
"""

from __future__ import annotations

import pandas as pd
from langgraph.graph import END, StateGraph

from ..trend import Criteria
from .nodes import (
    aggregator_agent,
    analysis_agent,
    coverage_agent,
    criteria_agent,
    critique_agent,
    make_retrieval_agent,
    retrieval_dispatch,
    retrieval_merge,
    route_after_coverage,
    route_after_critique,
)
from .state import AgentMode, GraphConfig, TrendState, new_state


def retrieval_node_names(n_agents: int) -> list[str]:
    return [f"Retrieval_{i}" for i in range(n_agents)]


def build_graph(n_retrieval_agents: int = GraphConfig().n_retrieval_agents):
    """Compile the cyclic agent graph.

    The retrieval fan-out width is a graph-construction parameter, not a
    runtime one, because LangGraph nodes are declared at build time. A config
    with a different ``n_retrieval_agents`` therefore needs its own compiled
    graph -- which is deliberate: the number of cooperating agents is part of
    the architecture, and the answer must not depend on it (a property the
    id-relabelling relation checks).
    """
    builder = StateGraph(TrendState)
    names = retrieval_node_names(n_retrieval_agents)

    builder.add_node("CriteriaAgent", criteria_agent)
    builder.add_node("RetrievalDispatch", retrieval_dispatch)
    for index, name in enumerate(names):
        builder.add_node(name, make_retrieval_agent(index))
    builder.add_node("RetrievalMerge", retrieval_merge)
    builder.add_node("CoverageAgent", coverage_agent)
    builder.add_node("AnalysisAgent", analysis_agent)
    builder.add_node("CritiqueAgent", critique_agent)
    builder.add_node("AggregatorAgent", aggregator_agent)

    builder.set_entry_point("CriteriaAgent")
    builder.add_edge("CriteriaAgent", "RetrievalDispatch")
    for name in names:
        builder.add_edge("RetrievalDispatch", name)  # fan out
        builder.add_edge(name, "RetrievalMerge")     # fan in
    builder.add_edge("RetrievalMerge", "CoverageAgent")

    # --- cycle 1: Coverage widens and re-runs the retrieval agents --------
    builder.add_conditional_edges(
        "CoverageAgent",
        route_after_coverage,
        {"retry": "RetrievalDispatch", "analyse": "AnalysisAgent"},
    )

    builder.add_edge("AnalysisAgent", "CritiqueAgent")

    # --- cycle 2: Critique sends a complaint back to Analysis -------------
    builder.add_conditional_edges(
        "CritiqueAgent",
        route_after_critique,
        {"recompute": "AnalysisAgent", "report": "AggregatorAgent"},
    )

    builder.add_edge("AggregatorAgent", END)
    return builder.compile()


#: Recursion budget. Must exceed the worst-case node visits implied by the
#: round caps and the retrieval fan-out, or LangGraph aborts a legitimately
#: long run.
DEFAULT_RECURSION_LIMIT = 120


def run_pipeline(
    frame: pd.DataFrame,
    filter_spec: Criteria,
    *,
    seed: int = 0,
    config: GraphConfig | None = None,
    graph=None,
    user_query: str = "",
    llm=None,
) -> TrendState:
    """Run the agent graph once and return the final state."""
    config = config or GraphConfig()
    if graph is None:
        graph = build_graph(config.n_retrieval_agents)
    state = new_state(frame, filter_spec, seed=seed, config=config,
                      user_query=user_query, llm=llm)
    return graph.invoke(
        state, config={"recursion_limit": DEFAULT_RECURSION_LIMIT}
    )
