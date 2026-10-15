"""The six agents of the design note.

Mapping to the brief's three control-flow requirements:

* **(a) feedback loop** - cycle 2, Critique/Validation -> Analysis. A rejection
  carries a specific complaint and flagged months, and Analysis recomputes
  only those months.
* **(b) conditional/iterative control** - cycle 1, Coverage -> Retrieval. The
  Coverage agent widens the binding criterion and re-runs retrieval until
  coverage is met or the round cap is reached.
* **(c) genuine dependency** - the Criteria agent sets ``query_mode``, and the
  Retrieval agents execute a *different algorithm* as a result: exact locality
  matching or great-circle radius search.

Agents are deterministic by default. In LLM mode four of them delegate their
*judgment* to a local model; the statistics stay deterministic Python in every
mode, because an LLM computing a median would make every metamorphic relation
meaningless.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from ..contract import CONTRACT_VERSION, MIN_SUFFICIENT_N
from ..trend import (
    Criteria,
    apply_criteria,
    compute_trend,
    haversine_km,
    month_window,
)
from .state import (
    AgentMode,
    CoverageVerdict,
    CritiqueVerdict,
    GraphConfig,
    TrendState,
    log_step,
)


def _is_llm(state: TrendState) -> bool:
    cfg: GraphConfig = state["config"]
    return cfg.agent_mode == AgentMode.LLM and state.get("llm") is not None


# ==========================================================================
# 1. Criteria Agent
# ==========================================================================

_CRITERIA_PROMPT = """You plan property searches over a Hyderabad housing dataset.

Decide how the search should be run, then reply with ONLY a JSON object.

Request: {query}

Available locality names include: {localities}

Reply with exactly these keys:
  "query_mode": either "EXACT_LOCALITY" (the request names specific localities)
                or "RADIUS" (the request is about an area, distance, or
                "near"/"around" somewhere)
  "reason": one short sentence

JSON:"""


def criteria_agent(state: TrendState) -> TrendState:
    """Turn the request into a filter spec and choose the retrieval algorithm.

    ``query_mode`` is the design note's genuine dependency: it does not change
    which rows Retrieval receives, it changes which algorithm Retrieval runs.
    """
    spec: Criteria = state["filter_spec"]

    if _is_llm(state) and state.get("user_query"):
        frame: pd.DataFrame = state["frame"]
        localities = ", ".join(
            frame["locality"].value_counts().head(12).index.tolist()
        )
        prompt = _CRITERIA_PROMPT.format(
            query=state["user_query"], localities=localities
        )
        decision, used_fallback = state["llm"].ask_json(
            prompt,
            seed=state.get("seed", 0),
            fallback={"query_mode": spec.query_mode, "reason": "fallback"},
            validate=lambda d: d.get("query_mode") in
            ("EXACT_LOCALITY", "RADIUS"),
        )
        mode = decision.get("query_mode", spec.query_mode)
        if mode == "RADIUS" and spec.center_lat is None:
            # The model asked for a radius search but the request carried no
            # centre. Refusing to invent one: fall back to exact matching and
            # record it, rather than silently geocoding a guess.
            mode = "EXACT_LOCALITY"
            decision["reason"] = (
                str(decision.get("reason", "")) + " [no centre supplied; "
                "exact matching used]"
            )
        spec = spec.with_(query_mode=mode)
        state["filter_spec"] = spec
        log_step(state, "CriteriaAgent", action="planned (LLM)",
                 query_mode=mode, llm_fallback=used_fallback,
                 reason=str(decision.get("reason", ""))[:90])
    else:
        log_step(state, "CriteriaAgent", action="planned (deterministic)",
                 query_mode=spec.query_mode, filter_spec=spec.describe())

    state["query_mode"] = spec.query_mode
    return state


# ==========================================================================
# 2. Retrieval Agents  (several, cooperating)
# ==========================================================================

def shard_of(listing_id: str, seed: int, n_agents: int) -> int:
    """Deterministic, seed-dependent assignment of a listing to an agent.

    A stable hash, not Python's randomised ``hash``, so a run is reproducible
    across processes -- without this, the id-relabelling relation would report
    violations caused by PYTHONHASHSEED rather than by the system.
    """
    digest = hashlib.sha256(f"{seed}:{listing_id}".encode()).digest()
    return digest[0] % n_agents


def make_retrieval_agent(agent_index: int):
    """Build one of the cooperating Retrieval agents.

    Each agent scans its own shard of the snapshot against the current filter
    spec, executing whichever algorithm ``query_mode`` selected. Agents write
    into an additive channel, so they genuinely run as parallel graph nodes
    rather than as a loop inside a single node.
    """

    def retrieval_agent(state: TrendState) -> TrendState:
        cfg: GraphConfig = state["config"]
        spec: Criteria = state.get("widened_filter_spec") or state["filter_spec"]
        frame: pd.DataFrame = state["frame"]
        seed = state.get("seed", 0)

        window = month_window(spec.window_end)
        matched = apply_criteria(frame, spec)
        matched = matched[matched["month"].isin(window)]

        if matched.empty:
            shard = matched
        else:
            assignment = matched["listing_id"].map(
                lambda lid: shard_of(lid, seed, cfg.n_retrieval_agents)
            )
            shard = matched[assignment == agent_index]

        entry = {
            "agent": agent_index,
            "round": state.get("retry_count", 0),
            "query_mode": spec.query_mode,
            "n_matched": int(len(shard)),
            "listing_ids": shard["listing_id"].tolist(),
        }
        log_step(state, f"RetrievalAgent[{agent_index}]",
                 query_mode=spec.query_mode, retrieved=int(len(shard)),
                 retry_round=state.get("retry_count", 0))
        return {"retrieval_report": [entry]}

    retrieval_agent.__name__ = f"retrieval_agent_{agent_index}"
    return retrieval_agent


def retrieval_dispatch(state: TrendState) -> TrendState:
    """Fan-out point for the cooperating Retrieval agents.

    Exists because LangGraph conditional edges take a single target per route
    key, so cycle 1 needs one node to return to before the agents run again.
    It also gives the trace an explicit marker for each retrieval round.
    """
    cfg: GraphConfig = state["config"]
    spec: Criteria = state.get("widened_filter_spec") or state["filter_spec"]
    log_step(state, "RetrievalDispatch",
             agents=cfg.n_retrieval_agents,
             query_mode=spec.query_mode,
             round=state.get("retry_count", 0))
    return state


def retrieval_merge(state: TrendState) -> TrendState:
    """Fan-in for the cooperating Retrieval agents.

    Reassembles this round's shards into ``raw_listings`` in a canonical order,
    so the merged result cannot depend on which agent finished first.

    Entries are selected by retrieval round rather than by clearing the
    channel: ``retrieval_report`` has an additive reducer (the agents are
    parallel nodes), and an additive channel cannot be emptied by a node
    return. Round-tagging keeps every round visible in the trace instead.
    """
    cfg: GraphConfig = state["config"]
    spec: Criteria = state.get("widened_filter_spec") or state["filter_spec"]
    frame: pd.DataFrame = state["frame"]
    current_round = state.get("retry_count", 0)

    ids: list[str] = []
    for entry in state.get("retrieval_report", []):
        if entry.get("round") == current_round:
            ids.extend(entry.get("listing_ids", []))

    merged = frame[frame["listing_id"].isin(set(ids))].sort_index()

    n_missing_coord = 0
    if spec.query_mode == "RADIUS":
        # Rows that match every non-geographic criterion and the window but
        # cannot be placed on the map: exactly what the radius query excluded.
        window = month_window(spec.window_end)
        candidates = apply_criteria(
            frame, spec.with_(query_mode="EXACT_LOCALITY", localities=None))
        candidates = candidates[candidates["month"].isin(window)]
        n_missing_coord = int(candidates["latitude"].isna().sum())

    state["raw_listings"] = merged
    state["n_no_coordinate"] = n_missing_coord
    log_step(state, "RetrievalMerge",
             agents=len({e["agent"] for e in state.get("retrieval_report", [])
                         if e.get("round") == current_round}),
             round=current_round,
             listings=int(len(merged)),
             excluded_no_coordinate=n_missing_coord)
    return state


# ==========================================================================
# 3. Coverage / Confidence Agent   (owns cycle 1)
# ==========================================================================

def _relax_price_band(c: Criteria, frame: pd.DataFrame) -> tuple[Criteria, str] | None:
    if c.price_min_inr is None and c.price_max_inr is None:
        return None
    lo = None if c.price_min_inr is None else c.price_min_inr * 0.75
    hi = None if c.price_max_inr is None else c.price_max_inr * 1.25
    return c.with_(price_min_inr=lo, price_max_inr=hi), "price band widened 25%"


def _relax_bhk(c: Criteria, frame: pd.DataFrame) -> tuple[Criteria, str] | None:
    if not c.bhk:
        return None
    widened = tuple(sorted({b + d for b in c.bhk for d in (-1, 0, 1) if b + d >= 1}))
    if widened == c.bhk:
        return None
    return c.with_(bhk=widened), f"BHK {list(c.bhk)} -> {list(widened)}"


def _locality_centres(frame: pd.DataFrame) -> pd.DataFrame:
    """Median coordinate of each named locality that has located listings."""
    located = frame.dropna(subset=["latitude", "longitude"])
    located = located[located["locality"] != "Unknown"]
    return located.groupby("locality")[["latitude", "longitude"]].median()


def _relax_geography(c: Criteria, frame: pd.DataFrame) -> tuple[Criteria, str] | None:
    """Widen whichever geographic constraint ``query_mode`` selected.

    RADIUS doubles the radius. EXACT_LOCALITY adds the nearest unselected
    localities -- by distance from the median of the selected localities'
    centres, ties broken by name -- until the added localities hold at least
    as many snapshot listings as the selected ones, so depth roughly doubles,
    like the radius lever (contracts/Coverage.md §3). Depth is counted over
    the whole frame, so row order, duplication and window shifts cannot
    change which localities are added.

    It never removes the locality constraint: dropping it made every run
    collapse to the whole metro, so a locality subset (MR M3) was compared
    with an identical whole-metro run and could not fail.
    """
    if c.query_mode == "RADIUS":
        if not c.radius_km:
            return None
        return (c.with_(radius_km=c.radius_km * 2.0),
                f"radius {c.radius_km:.1f}km -> {c.radius_km * 2.0:.1f}km")
    if not c.localities:
        return None
    centres = _locality_centres(frame)
    selected = centres.loc[centres.index.isin(c.localities)]
    others = centres.loc[~centres.index.isin(c.localities)]
    if selected.empty or others.empty:
        return None                 # nothing to measure from, or nothing left
    distance = haversine_km(
        float(selected["latitude"].median()), float(selected["longitude"].median()),
        others["latitude"].to_numpy(dtype=float),
        others["longitude"].to_numpy(dtype=float),
    )
    depth = frame["locality"].value_counts()
    ranked = (pd.DataFrame({"locality": others.index, "km": distance})
              .sort_values(["km", "locality"], kind="mergesort"))
    target = int(depth.reindex(list(c.localities)).fillna(0).sum())
    added: list[str] = []
    gained = 0
    for name in ranked["locality"]:
        added.append(name)
        gained += int(depth.get(name, 0))
        if gained >= max(target, 1):
            break
    added = tuple(added)
    return c.with_(localities=tuple(c.localities) + added), (
        f"localities widened by the {len(added)} nearest: {list(added)}"
    )


_RELAXATIONS = (_relax_price_band, _relax_bhk, _relax_geography)

#: Canonical lever names, aligned with _RELAXATIONS. Used for the control-path
#: signature, which must not depend on the criteria values themselves.
_LEVER_NAMES = ("price_band", "bhk", "geography")


def _geographic_spread(listings: pd.DataFrame) -> int:
    """How many distinct localities the retrieved sample touches."""
    if listings.empty:
        return 0
    return int(listings["locality"].nunique())


def coverage_agent(state: TrendState) -> TrendState:
    """Score coverage, and decide whether to widen and re-retrieve.

    This owns cycle 1 -- the brief's conditional/iterative control step. The
    widened spec is written here (as the design note specifies) rather than
    sent back to the Criteria agent, so Criteria runs exactly once per request.
    """
    cfg: GraphConfig = state["config"]
    spec: Criteria = state.get("widened_filter_spec") or state["filter_spec"]
    listings: pd.DataFrame = state["raw_listings"]
    window = month_window(spec.window_end)

    counts = listings["month"].value_counts() if not listings.empty else {}
    sufficient = [m for m in window
                  if (counts.get(m, 0) if hasattr(counts, "get") else 0)
                  >= MIN_SUFFICIENT_N]
    score = len(sufficient) / len(window)
    spread = _geographic_spread(listings)

    state["coverage_score"] = score
    enough = score >= cfg.coverage_target
    state["coverage_verdict"] = (
        CoverageVerdict.SUFFICIENT.value if enough
        else CoverageVerdict.INSUFFICIENT.value
    )

    will_retry = (not enough
                  and state.get("retry_count", 0) < cfg.max_retry_rounds)

    if will_retry:
        cursor = state.get("relax_cursor", 0)
        widened = None
        # Advance through the levers, using each at most once, so a lever that
        # can always widen (BHK) does not starve the binding one (geography).
        while cursor < len(_RELAXATIONS):
            result = _RELAXATIONS[cursor](spec, state["frame"])
            cursor += 1
            if result is not None:
                widened, note = result
                state["widened_filter_spec"] = widened
                state["relax_cursor"] = cursor
                state.setdefault("relaxations", []).append(note)
                state.setdefault("relax_levers", []).append(_LEVER_NAMES[cursor - 1])
                break
        state["relax_cursor"] = cursor
        if widened is None:
            will_retry = False          # no lever left; stop rather than spin

    if will_retry:
        # The round counter also selects which retrieval entries the merge
        # consumes, so incrementing it is what makes the next pass fresh.
        state["retry_count"] = state.get("retry_count", 0) + 1

    log_step(state, "CoverageAgent",
             coverage_score=round(score, 4),
             target=cfg.coverage_target,
             sufficient_months=len(sufficient),
             geographic_spread=spread,
             verdict=state["coverage_verdict"],
             decision=("WIDEN and re-retrieve (cycle 1)" if will_retry
                       else "PROCEED"),
             relaxation=(state["relaxations"][-1]
                         if will_retry and state.get("relaxations") else None))

    state["retry_requested"] = will_retry
    return state


def route_after_coverage(state: TrendState) -> str:
    """Conditional edge for cycle 1."""
    return "retry" if state.get("retry_requested") else "analyse"


# ==========================================================================
# 4. Analysis Agent
# ==========================================================================

def _robust_z(values: np.ndarray) -> np.ndarray:
    """MAD-based robust z-score on log price-per-sqft.

    Log scale because price per unit area is right-skewed and multiplicative;
    MAD rather than standard deviation because the contaminating points are
    exactly what must not be allowed to set the threshold.
    """
    if values.size == 0:
        return values
    logged = np.log(np.clip(values, 1e-9, None))
    median = np.median(logged)
    mad = np.median(np.abs(logged - median))
    if mad <= 0:
        return np.zeros_like(logged)
    return 0.6745 * (logged - median) / mad


#: Lower bound of the "grey zone". Listings above the hard threshold are
#: rejected deterministically; those between this and the hard threshold are
#: statistically unusual but not conclusively wrong, which is exactly where a
#: model reading the description can add something arithmetic cannot. Scoping
#: the model to this band also bounds the number of calls per run.
GREY_ZONE_Z = 2.0

#: Most listings sent to the model in a single call. Batched per month so cost
#: scales with flagged months, not with listings.
REVIEW_BATCH = 12

_REVIEW_PROMPT = """You check property listings for data-entry errors.

Each listing below is statistically unusual for its month. For each one,
decide whether its DESCRIPTION is consistent with its stated price and area.
Flag a listing ONLY if the text clearly contradicts the numbers -- for example
a plot of land priced as a flat, or an area the text contradicts. Unusual but
internally consistent luxury listings are NOT errors.

{listings}

Reply with ONLY a JSON object: {{"suspect_numbers": [1, 3]}}
listing the NUMBERS of the inconsistent listings.
Use an empty list if all of them are internally consistent.

JSON:"""


def _llm_review_rejections(
    state: TrendState, candidates: pd.DataFrame, cfg: GraphConfig
) -> set:
    """Ask the model which grey-zone listings the text contradicts.

    Returns frame index labels to reject. Only listings whose robust z-score
    falls between GREY_ZONE_Z and the hard threshold are considered, so the
    model is never asked to re-derive what the arithmetic already settles.
    """
    if candidates.empty:
        return set()
    llm = state["llm"]
    seed = state.get("seed", 0)
    reject: set = set()

    # Pick which months to review before calling anything, so the cost is
    # bounded and the choice is deterministic (ties broken by month name).
    grey_by_month: dict[str, pd.DataFrame] = {}
    for month, group in candidates.groupby("month"):
        z = np.abs(_robust_z(group["psf_inr"].to_numpy(dtype=float)))
        grey = group[(z > GREY_ZONE_Z) & (z <= cfg.robust_z_threshold)]
        if not grey.empty:
            grey_by_month[str(month)] = grey
    chosen = sorted(grey_by_month,
                    key=lambda m: (-len(grey_by_month[m]), m))[:cfg.max_review_months]

    for month in chosen:
        grey = grey_by_month[month].nlargest(REVIEW_BATCH, "psf_inr")
        # Listings are presented by POSITION, never by listing id.
        #
        # The ids used to appear in the prompt, and the metamorphic relations
        # caught what that costs: a bijective relabelling of ids changed the
        # prompt text, the model answered differently, different listings were
        # rejected, and the trend moved -- a 0.630 violation rate on the
        # relabelling relation and 0.417 on duplication. A listing's
        # identifier carries no information about whether its description
        # corroborates its price, so showing it lets an identity change
        # influence a judgment that must not depend on it.
        #
        # Positions are assigned after a deterministic sort on the fields the
        # judgment is actually about, so the prompt is a function of the
        # listings' content alone.
        # The batch is CONTENT-ADDRESSED, not row-addressed.
        #
        # Three faults the metamorphic relations found, all closed here:
        #
        # 1. Listing ids appeared in the prompt, so a bijective relabelling
        #    changed the text the model saw (0.630 violation rate). Listings
        #    are now presented by position.
        # 2. The ordering sorted on a subset of the displayed fields, so
        #    listings tied on (psf, price, area) kept their input order and
        #    reordering the rows changed the prompt. The sort is now a total
        #    order over every field the prompt shows.
        # 3. Taking the top N of a duplicated set returns N/2 distinct
        #    listings twice rather than N distinct ones, so duplication
        #    changed the batch (0.417). The batch is now deduplicated on
        #    displayed content, and a verdict applies to EVERY row carrying
        #    that content -- which is also what makes counts double exactly,
        #    since rejecting one twin and not the other would not.
        display_cols = ["psf_inr", "price_inr", "area_sqft",
                        "property_type", "description"]
        ordered = grey.sort_values(display_cols, ascending=False,
                                   kind="mergesort")
        batch = ordered.drop_duplicates(subset=display_cols).head(REVIEW_BATCH)

        lines = []
        for position, row in enumerate(batch.itertuples(index=False), start=1):
            description = str(getattr(row, "description", "") or "")[:220]
            lines.append(
                f"{position}. price=Rs {row.price_inr:,.0f} "
                f"area={row.area_sqft:,.0f} sqft "
                f"({row.psf_inr:,.0f}/sqft) type={row.property_type}\n"
                f"   text: {description}"
            )
        verdict, _ = llm.ask_json(
            _REVIEW_PROMPT.format(listings="\n".join(lines)),
            seed=seed,
            fallback={"suspect_numbers": []},
            validate=lambda d: isinstance(d.get("suspect_numbers"), list),
        )
        flagged_positions = set()
        for value in verdict.get("suspect_numbers", []):
            try:
                flagged_positions.add(int(value))
            except (TypeError, ValueError):
                continue

        # Map each flagged position to its content, then reject every row in
        # the month carrying that content.
        flagged_content = {
            tuple(batch.iloc[position - 1][col] for col in display_cols)
            for position in flagged_positions
            if 1 <= position <= len(batch)
        }
        if flagged_content:
            keys = grey[display_cols].apply(tuple, axis=1)
            reject |= set(grey.index[keys.isin(flagged_content)])
    return reject


def _outlier_mask(group: pd.DataFrame, cfg: GraphConfig) -> pd.Series:
    """Rows a targeted recomputation rejects: contextual or self-inconsistent."""
    psf = group["psf_inr"].to_numpy(dtype=float)
    outlier = np.abs(_robust_z(psf)) > cfg.robust_z_threshold

    area_claim = group["area_sqm_raw"].to_numpy(dtype=float) * 10.7639104
    area_bad = np.abs(group["area_sqft"].to_numpy(dtype=float) / area_claim - 1.0)
    area_bad = np.where(np.isfinite(area_bad), area_bad, 0.0) > cfg.cross_field_tolerance

    price_claim = group["price_display_inr"].to_numpy(dtype=float)
    price_bad = np.abs(group["price_inr"].to_numpy(dtype=float) / price_claim - 1.0)
    price_bad = np.where(np.isfinite(price_bad), price_bad, 0.0) > cfg.cross_field_tolerance

    return pd.Series(outlier | area_bad | price_bad, index=group.index)


def analysis_agent(state: TrendState) -> TrendState:
    """Compute the output contract. On a critique complaint, recompute only the
    flagged months, rejecting contextual outliers within them.

    Recomputing selectively is the point of cycle 2: validating every listing
    on every run is wasteful and also discards legitimate luxury stock, so the
    escalation is targeted at the months whose aggregate looks wrong.
    """
    cfg: GraphConfig = state["config"]
    spec: Criteria = state.get("widened_filter_spec") or state["filter_spec"]
    listings: pd.DataFrame = state["raw_listings"]
    complaint = state.get("critique_complaint")
    flagged = set(state.get("flagged_months", []))

    rejected = 0
    working = listings
    if complaint and flagged and not listings.empty:
        candidates = listings[listings["month"].isin(flagged)]
        if cfg.group_outliers_by_month:
            drop: set = set()
            for _, group in candidates.groupby("month"):
                mask = _outlier_mask(group, cfg)
                drop |= set(group.index[mask.to_numpy()])
            if _is_llm(state):
                # The model only rules on the grey zone; the arithmetic keeps
                # the clear-cut cases.
                drop |= _llm_review_rejections(state, candidates, cfg)
            rejected = len(drop)
            working = listings[~listings.index.isin(drop)]
        else:
            # Original behaviour: the threshold is computed per (retrieval
            # shard, month), so the accepted set depends on how many retrieval
            # agents happened to be running. Retained behind the flag so the
            # root-cause analysis stays reproducible.
            seed = state.get("seed", 0)
            drop = set()
            shard_ids = candidates["listing_id"].map(
                lambda lid: shard_of(lid, seed, cfg.n_retrieval_agents)
            )
            for shard_index in range(cfg.n_retrieval_agents):
                shard = candidates[shard_ids == shard_index]
                for _, group in shard.groupby("month"):
                    mask = _outlier_mask(group, cfg)
                    drop |= set(group.index[mask.to_numpy()])
            rejected = len(drop)
            working = listings[~listings.index.isin(drop)]

    # Every computation starts again from raw_listings with the cumulative
    # flagged months, so this pass's count IS the total; adding it to the
    # previous pass's count double-counted when more than one round ran.
    state["n_rejected_outliers"] = rejected
    # The critique judges the listings the statistics were computed from.
    state["analysed_listings"] = working

    provenance = {
        "contract_version": CONTRACT_VERSION,
        # None for frames not built by load_canonical (e.g. the synthetic
        # snapshot), so a report never names a snapshot it did not come from.
        "snapshot_sha256": state["frame"].attrs.get("snapshot_sha256"),
        "seed": state.get("seed", 0),
        "agent_mode": state["config"].agent_mode.value,
        "query_mode": spec.query_mode,
        "retry_count": state.get("retry_count", 0),
        "critique_rounds": state.get("critique_rounds", 0),
        "relaxations": list(state.get("relaxations", [])),
        "relax_levers": list(state.get("relax_levers", [])),
        "coverage_score": state.get("coverage_score"),
        "n_rejected_outliers": state.get("n_rejected_outliers", 0),
        "flagged_months": sorted(flagged),
        "n_no_coordinate": state.get("n_no_coordinate", 0),
    }
    if state.get("llm") is not None:
        provenance.update(state["llm"].stats.as_dict())

    report = compute_trend(working, spec, provenance=provenance)
    state["trend_stats"] = report
    log_step(state, "AnalysisAgent",
             mode=("targeted recomputation" if complaint else "full"),
             listings=report.n_listings_total,
             recomputed_months=sorted(flagged) if complaint else [],
             rejected_this_pass=rejected,
             sufficient_months=len(report.sufficient_months()),
             move_pct=(None if report.yoy_median_psf_pct is None
                       else round(report.yoy_median_psf_pct, 2)))
    return state


# ==========================================================================
# 5. Critique / Validation Agent   (owns cycle 2)
# ==========================================================================

_CRITIQUE_PROMPT = """You review a twelve-month housing price trend for errors.

Monthly medians (price per sqft):
{table}

A month is suspicious if its median is wildly out of line with its neighbours
in a way that a real market would not produce.

Reply with ONLY a JSON object: {{"suspect_months": ["YYYY-MM", ...], "reason": "..."}}
Use an empty list if the series looks plausible.

JSON:"""


def critique_agent(state: TrendState) -> TrendState:
    """Validate the computed trend; on failure send a specific complaint back.

    This owns cycle 2 -- the brief's feedback loop. The complaint names the
    months at fault so Analysis can recompute only those.
    """
    cfg: GraphConfig = state["config"]
    report = state["trend_stats"]
    # The listings the report was computed from, so after a recomputation the
    # critique checks whether the rejection actually cleaned the month.
    listings: pd.DataFrame = state.get("analysed_listings", state["raw_listings"])
    assert report is not None

    flagged: set[str] = set()
    reasons: list[str] = []

    # Structural check: a month with listings but no computable statistic.
    for stat in report.monthly:
        if stat.n_active and stat.median_psf is None:
            flagged.add(stat.month)
            reasons.append(f"{stat.month}: listings present but no median")

    # The deterministic checks ALWAYS run. In LLM mode the model adds its
    # judgment on top; it does not get to switch the floor off.
    #
    # An earlier version let the model replace these checks. Validated against
    # qwen2.5:3b, the model returned no suspect months at all, so cycle 2 never
    # fired, no contamination was rejected, and the headline came out -10.9%
    # instead of -13.6%. LLM mode was strictly worse at the job the arithmetic
    # already does reliably. Augmenting keeps the loop's floor deterministic
    # while still letting the model contribute.
    for month, change in zip(report.window_months, report.pct_change_series()):
        if change is not None and abs(change) > cfg.jump_threshold_pct:
            stat = report.month_stat(month)
            if stat and stat.n_active:
                flagged.add(month)
                reasons.append(f"{month}: {change:+.1f}% month-on-month")
    if not listings.empty:
        for month, group in listings.groupby("month"):
            z = _robust_z(group["psf_inr"].to_numpy(dtype=float))
            if np.any(np.abs(z) > cfg.robust_z_threshold):
                flagged.add(str(month))

    if _is_llm(state):
        # Canonical units (rupees per sqft), NOT the report's display units.
        #
        # The table used to carry display-scaled medians, and the
        # unit-invariance relation caught the consequence: re-expressing the
        # report in lakh per square metre changed these numbers, so different
        # months were flagged and different listings rejected -- "counts
        # changed under a display-unit change". A judgment about whether a
        # month looks anomalous must not depend on the units it is shown in.
        from ..contract import AREA_SCALE, CURRENCY_SCALE
        to_canonical = (
            AREA_SCALE[report.area_unit] / CURRENCY_SCALE[report.currency_unit]
        )
        # Listing counts are deliberately NOT shown.
        #
        # They were, and the duplication relation caught the cost: doubling
        # the dataset doubles every count, a count-aware judge then flags
        # different months, different listings are rejected, and the medians
        # move -- which is exactly what that relation forbids. It violated
        # 0.417 on the Kaggle sweep.
        #
        # Withholding them loses nothing real: the deterministic rule this
        # judgment augments flags on month-on-month movement and on the
        # presence of contextual outliers, and reads no counts either. Giving
        # the model the same information set as its own floor is what makes
        # the two modes comparable.
        rows = "\n".join(
            f"  {s.month}  median="
            f"{0 if s.median_psf is None else round(s.median_psf * to_canonical)}"
            for s in report.monthly
        )
        decision, used_fallback = state["llm"].ask_json(
            _CRITIQUE_PROMPT.format(table=rows),
            seed=state.get("seed", 0),
            fallback={"suspect_months": [], "reason": "fallback"},
            validate=lambda d: isinstance(d.get("suspect_months"), list),
        )
        valid_months = set(report.window_months)
        llm_flagged = {str(m) for m in decision.get("suspect_months", [])
                       if str(m) in valid_months}
        extra = llm_flagged - flagged
        flagged |= llm_flagged
        if extra:
            reasons.append(f"model additionally flagged {sorted(extra)}")
        state["_llm_critique_fallback"] = used_fallback

    already = set(state.get("flagged_months", []))
    new_flags = flagged - already
    will_recompute = (bool(new_flags)
                      and state.get("critique_rounds", 0) < cfg.max_critique_rounds)

    state["critique_verdict"] = (
        CritiqueVerdict.REJECTED.value if will_recompute
        else CritiqueVerdict.APPROVED.value
    )
    state["critique_complaint"] = (
        {"flagged_months": sorted(flagged), "reasons": reasons[:6]}
        if will_recompute else None
    )

    log_step(state, "CritiqueAgent",
             flagged=sorted(flagged), new_flags=sorted(new_flags),
             verdict=state["critique_verdict"],
             decision=("REJECT -> recompute flagged months (cycle 2)"
                       if will_recompute else "APPROVE"),
             critique_round=state.get("critique_rounds", 0),
             reason=reasons[0] if reasons else None)

    if will_recompute:
        state["flagged_months"] = sorted(flagged)
        state["critique_rounds"] = state.get("critique_rounds", 0) + 1
    state["recompute_requested"] = will_recompute
    return state


def route_after_critique(state: TrendState) -> str:
    """Conditional edge for cycle 2."""
    return "recompute" if state.get("recompute_requested") else "report"


# ==========================================================================
# 6. Aggregator / Report Agent
# ==========================================================================

_NARRATIVE_PROMPT = """Summarise this housing data in two short sentences of
plain English for a home buyer. Use only the figures given. Do not add any
other number, place or date. Mention the size and direction of the price
change, how many of the twelve months were reliable, the area covered, and how
many listings were analysed. Output nothing but the two sentences.

price change in median per sqft: {move}
reliable months: {n_sufficient} out of 12
area covered: {scope}
listings analysed: {total}
"""


#: Numbers the narrative is allowed to contain. Anything else means the model
#: invented a figure, which for a user-facing summary is a defect rather than a
#: stylistic quibble.
_NUMBER = __import__("re").compile(r"\d[\d,]*\.?\d*")


def _narrative_is_faithful(text: str, allowed: set[str]) -> tuple[bool, str]:
    """Reject a summary that invents figures or parrots the instructions.

    A 0.5B model, given the facts, produced "12 months of reliable listings"
    when 6 were reliable, restated a percentage change as a price, and copied a
    parenthetical instruction into its output. None of those are acceptable in
    text shown to a user, and all of them are detectable: every numeric token
    must come from the supplied facts.
    """
    lowered = text.lower()
    for leak in ("price change in median per sqft:", "reliable months:",
                 "area covered:", "listings analysed:", "output nothing",
                 "use only the figures", "plain english for a home buyer"):
        if leak in lowered:
            return False, f"instruction leaked into output ({leak!r})"
    for token in _NUMBER.findall(text):
        normalised = token.rstrip(".").replace(",", "")
        if normalised and normalised not in allowed:
            return False, f"invented figure {token!r}"
    return True, ""


def aggregator_agent(state: TrendState) -> TrendState:
    """Assemble the approved trend and render the user-facing summary."""
    report = state["trend_stats"]
    assert report is not None
    state["final_report"] = report

    first, last = report.window_months[0], report.window_months[-1]
    move = report.yoy_median_psf_pct
    top = (report.locality_rankings[0].locality
           if report.locality_rankings else "n/a")

    if _is_llm(state):
        # Describe the scope explicitly. A 0.5B model fused "most expensive
        # locality" with the trend itself and reported a metro-wide decline as
        # being "in the Gandipet locality"; naming the scope and labelling the
        # ranking fact as separate is what stopped that.
        spec: Criteria = state.get("widened_filter_spec") or state["filter_spec"]
        if spec.query_mode == "RADIUS":
            scope = (f"within {spec.radius_km:.0f} km of "
                     f"{spec.center_lat:.3f}, {spec.center_lon:.3f}")
        elif spec.localities:
            scope = ", ".join(spec.localities)
        else:
            scope = "the whole Hyderabad metro area"
        n_sufficient = len(report.sufficient_months())
        move_text = "unavailable" if move is None else f"{move:+.1f}%"
        total_text = f"{report.n_listings_total:,}"
        prompt = _NARRATIVE_PROMPT.format(
            scope=scope, n_sufficient=n_sufficient,
            move=move_text, total=total_text,
        )
        allowed = {"12", str(n_sufficient), total_text.replace(",", ""),
                   move_text.lstrip("+-").rstrip("%")}
        if move is not None:
            allowed.add(f"{abs(move):.1f}")
        deterministic = _deterministic_narrative(state, report)
        text = state["llm"].ask_text(
            prompt, seed=state.get("seed", 0), fallback=deterministic,
        ).strip()

        faithful, why = _narrative_is_faithful(text, allowed)
        if not faithful:
            # Counted as a fallback: the model was reached but its prose was
            # not usable, and the reported fallback rate must reflect that.
            state["llm"].stats.fallbacks += 1
            log_step(state, "AggregatorAgent",
                     narrative_rejected=why, using="deterministic template")
            text = deterministic
        elif text != deterministic:
            caveat = _partial_month_caveat(report)
            if caveat:
                text = f"{text} {caveat}"
        state["narrative"] = text
    else:
        state["narrative"] = _deterministic_narrative(state, report)

    # Refresh the LLM accounting now that every call for this run has been
    # made. Analysis writes provenance mid-pipeline, so without this the
    # reported call count and fallback rate would omit the critique and
    # narrative calls -- understating exactly the number we promised to
    # report honestly. ``provenance`` is a plain dict on a frozen dataclass,
    # so updating it in place is legitimate; the statistics are untouched.
    if state.get("llm") is not None:
        report.provenance.update(state["llm"].stats.as_dict())

    log_step(state, "AggregatorAgent",
             chars=len(state["narrative"]),
             coverage_score=round(state.get("coverage_score", 0.0), 4),
             llm_calls=(None if state.get("llm") is None
                        else state["llm"].stats.calls),
             llm_fallback_rate=(None if state.get("llm") is None
                                else round(state["llm"].stats.fallback_rate, 4)))
    return state


def _partial_month_caveat(report) -> str:
    """Contracts/Aggregator.md §2.4. Added by code, never by the model, so it
    cannot be dropped or reworded into a claim about a full month."""
    partial = [m.month for m in report.monthly if m.is_partial_month]
    if not partial:
        return ""
    return (f"{partial[0]} is a partial month: the snapshot ends on "
            f"26 Aug 2023, so it is reported as observed, not extrapolated.")


def _deterministic_narrative(state: TrendState, report) -> str:
    first, last = report.window_months[0], report.window_months[-1]
    move = report.yoy_median_psf_pct
    direction = ("flat" if move is None or abs(move) < 0.5
                 else "risen" if move > 0 else "fallen")

    lines = [
        f"Hyderabad asking-price trend, {first} to {last}.",
        f"{report.n_listings_total:,} listings matched the criteria.",
    ]
    if move is None:
        lines.append(
            "Too few months met the sufficiency threshold to state a trend."
        )
    else:
        lines.append(
            f"Median asking price per sqft has {direction} {abs(move):.1f}% "
            f"across the {report.yoy_span_months} months with adequate "
            f"listing depth (the window spans 12)."
        )
    caveat = _partial_month_caveat(report)
    if caveat:
        lines.append(caveat)
    if report.locality_rankings:
        top = report.locality_rankings[0]
        lines.append(
            f"Most expensive locality by median: {top.locality} "
            f"({top.median_psf:,.0f} per sqft, n={top.n_active})."
        )
    if report.provenance.get("relaxations"):
        lines.append(
            "The original query was too narrow to answer and was relaxed: "
            + "; ".join(report.provenance["relaxations"]) + "."
        )
    if report.provenance.get("n_rejected_outliers"):
        lines.append(
            f"Targeted recomputation rejected "
            f"{report.provenance['n_rejected_outliers']} suspect listings in "
            f"{len(report.provenance['flagged_months'])} flagged months."
        )
    return " ".join(lines)
