"""Shared state for the agent graph.

Field names follow the design note's Reads/Writes table so the document and
the implementation describe the same object. Agent-facing names
(``filter_spec``, ``raw_listings``, ``coverage_score``, ``trend_stats``,
``critique_complaint``) are the note's; the additions below it are things the
note's contract lacked and measurement showed were needed.

``trace`` is the execution log the brief requires as evidence that a loop
actually fires at run time.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import operator
from typing import Annotated, Any, TypedDict

import pandas as pd

from ..contract import TrendReport
from ..trend import Criteria


class AgentMode(str, Enum):
    """Whether judgment steps are deterministic Python or a local model.

    DETERMINISTIC is the default and is what every committed result set was
    produced with; it is also what the test suite runs, so the suite stays
    fast and does not depend on a model being present.
    """

    DETERMINISTIC = "DETERMINISTIC"
    LLM = "LLM"


class CoverageVerdict(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class CritiqueVerdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class GraphConfig:
    """Control-flow knobs. Both cycles are capped, so termination is assured."""

    #: Share of the twelve window months that must have adequate depth before
    #: the Coverage agent stops widening.
    coverage_target: float = 0.50

    #: Cap on cycle 1 (Coverage -> Retrieval).
    max_retry_rounds: int = 3

    #: Cap on cycle 2 (Critique -> Analysis). One round, deliberately.
    #:
    #: A second round is unsound: the Critique agent's flagged set GROWS
    #: between rounds, and which months look anomalous depends on the whole
    #: slice -- so widening a price band can cause a month to be filtered in
    #: one run and not another. Measured on the count-monotonicity relation:
    #: 2/16 violations at two rounds, 0/16 at one. The robust threshold is
    #: also relative, so the filter is not idempotent -- adding one listing to
    #: a month changes the z-score of every listing already in it.
    #:
    #: The cycle still fires; this caps iterations, it does not remove the
    #: back-edge.
    max_critique_rounds: int = 1

    #: Number of cooperating Retrieval agents. The brief asks for "several
    #: cooperating agents each scan listings", so retrieval is genuinely
    #: fanned out rather than looped inside one node.
    n_retrieval_agents: int = 4

    #: MAD-based robust outlier cut used by targeted recomputation.
    robust_z_threshold: float = 3.5

    #: Most months whose grey-zone listings are sent to the model per
    #: recomputation.
    #:
    #: Bounded because the review dominates LLM cost: with all twelve months
    #: flagged, one pipeline run issued 12 review calls plus 4 others, so a
    #: full sweep (1,188 checks x 2 runs) would be ~38,000 calls -- over the
    #: Kaggle session limit even on GPU. Reviewing the three months with the
    #: most grey-zone candidates cuts that to ~7 calls per run while keeping
    #: the model on the critical path. Months are chosen by candidate count,
    #: deterministically, so the choice does not vary between source and
    #: follow-up runs of a metamorphic relation.
    max_review_months: int = 3

    #: Month-on-month move the Critique agent treats as implausible.
    jump_threshold_pct: float = 25.0

    #: Tolerated disagreement between independent restatements of a field.
    cross_field_tolerance: float = 0.01

    #: How the Analysis agent groups listings before computing the robust
    #: outlier threshold. False reproduces the original fault, in which the
    #: threshold was computed per (retrieval shard, month) and the answer
    #: therefore depended on how many retrieval agents happened to be running.
    #: Kept as a flag so the root-cause analysis stays reproducible.
    group_outliers_by_month: bool = True

    # -- LLM configuration ---------------------------------------------
    agent_mode: AgentMode = AgentMode.DETERMINISTIC
    llm_model: str = "qwen2.5:3b-instruct-q4_K_M"
    llm_host: str = "http://localhost:11434"
    llm_max_attempts: int = 3


class TrendState(TypedDict, total=False):
    # --- inputs -------------------------------------------------------
    user_query: str                  # free-text request (LLM mode)
    frame: pd.DataFrame              # the frozen snapshot
    filter_spec: Criteria            # the note's filter_spec
    seed: int
    config: GraphConfig
    llm: Any                         # LLMClient | None

    # --- Criteria agent ----------------------------------------------
    query_mode: str                  # EXACT_LOCALITY | RADIUS

    # --- Retrieval agents --------------------------------------------
    raw_listings: pd.DataFrame
    #: One entry per cooperating Retrieval agent. Additive reducer because the
    #: retrieval agents are parallel graph nodes writing this key at the same
    #: time; a plain channel would make LangGraph reject the concurrent write.
    retrieval_report: Annotated[list[dict[str, Any]], operator.add]
    n_no_coordinate: int             # excluded by a RADIUS query

    # --- Coverage / Confidence agent (owns cycle 1) -------------------
    coverage_score: float
    coverage_verdict: str
    widened_filter_spec: Criteria | None
    retry_count: int
    relaxations: list[str]
    relax_levers: list[str]          # canonical lever names, for path signature
    relax_cursor: int

    # --- Analysis agent ----------------------------------------------
    trend_stats: TrendReport | None
    #: The listings ``trend_stats`` was computed from (raw_listings minus any
    #: rejected outliers); what the Critique agent inspects.
    analysed_listings: pd.DataFrame
    flagged_months: list[str]
    n_rejected_outliers: int

    # --- Critique / Validation agent (owns cycle 2) -------------------
    critique_verdict: str
    critique_complaint: dict[str, Any] | None
    critique_rounds: int

    # --- Aggregator / Report agent -----------------------------------
    final_report: TrendReport | None
    narrative: str

    # --- routing flags ------------------------------------------------
    # These MUST be declared channels: LangGraph derives its state channels
    # from these annotations and silently discards updates to undeclared keys,
    # which would make both conditional edges dead and the cycles unreachable.
    retry_requested: bool
    recompute_requested: bool

    # --- observability ------------------------------------------------
    trace: list[dict[str, Any]]


def new_state(
    frame: pd.DataFrame,
    filter_spec: Criteria,
    *,
    seed: int = 0,
    config: GraphConfig | None = None,
    user_query: str = "",
    llm: Any = None,
) -> TrendState:
    return TrendState(
        user_query=user_query,
        frame=frame,
        filter_spec=filter_spec,
        seed=seed,
        config=config or GraphConfig(),
        llm=llm,
        query_mode=filter_spec.query_mode,
        raw_listings=frame.iloc[0:0],
        retrieval_report=[],
        n_no_coordinate=0,
        coverage_score=0.0,
        coverage_verdict=CoverageVerdict.INSUFFICIENT.value,
        widened_filter_spec=None,
        retry_count=0,
        relaxations=[],
        relax_levers=[],
        relax_cursor=0,
        trend_stats=None,
        analysed_listings=frame.iloc[0:0],
        flagged_months=[],
        n_rejected_outliers=0,
        critique_verdict=CritiqueVerdict.REJECTED.value,
        critique_complaint=None,
        critique_rounds=0,
        final_report=None,
        narrative="",
        retry_requested=False,
        recompute_requested=False,
        trace=[],
    )


def log_step(state: TrendState, agent: str, **detail: Any) -> dict[str, Any]:
    """Append one line to the execution trace and return it."""
    entry = {"step": len(state.get("trace", [])) + 1, "agent": agent, **detail}
    state.setdefault("trace", []).append(entry)
    return entry
