# Credits: Paridhi Mittal. Full attribution: CREDITS.md.
"""A readable form of the execution trace, for the dashboard and the UI export.

The raw trace (``state["trace"]``) logs every field each agent records. This
keeps one line per step that matters -- retrieval rounds, coverage decisions,
analysis passes, critique verdicts -- and marks the steps where a cycle fired,
so a reader can follow both loops changing the answer.
"""
from __future__ import annotations

from typing import Any


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def readable_trace(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``[{step, agent, detail, cycle, move_pct}]``; ``cycle`` is 1, 2 or None,
    ``move_pct`` the headline after an Analysis step (else None)."""
    out = []
    for e in entries:
        agent, cycle, detail, move = e["agent"], None, None, None
        if agent == "RetrievalMerge":
            detail = (f"{e.get('agents')} agents, round {e.get('round')}: "
                      f"{e.get('listings')} listings")
        elif agent == "CoverageAgent":
            detail = (f"coverage {e.get('coverage_score', 0):.2f} "
                      f"({e.get('covered_months')} of {e.get('attainable_months')} "
                      f"attainable months) → {e.get('verdict')}")
            if e.get("relaxation"):
                detail += f": {str(e['relaxation']).split(':')[0]}"
            if "cycle 1" in str(e.get("decision", "")):
                cycle = 1
        elif agent == "AnalysisAgent":
            move = e.get("move_pct")
            detail = f"{e.get('mode')}: move {move}%"
            if e.get("rejected_this_pass"):
                detail += f", {_plural(e['rejected_this_pass'], 'outlier')} rejected"
        elif agent == "CritiqueAgent":
            detail = (f"{_plural(len(e.get('flagged') or []), 'month')} flagged"
                      f" → {e.get('verdict')}")
            if "cycle 2" in str(e.get("decision", "")):
                cycle = 2
        elif agent == "AggregatorAgent" and "chars" in e:
            detail = "report assembled"
        elif agent == "CriteriaAgent":
            detail = f"planned: query mode {e.get('query_mode')}"
        if detail:
            out.append({"step": e["step"], "agent": agent, "detail": detail,
                        "cycle": cycle, "move_pct": move})
    return out
