"""The LLM layer: parsing, caching, seeding, fallbacks, and graph wiring.

These tests use a scripted backend, never a real model. That is deliberate:
the purpose is to prove the plumbing -- that seeds reach the model, that
malformed replies are retried and then fall back *and are counted*, and that
the agent graph runs end to end in LLM mode with both cycles still firing.
Whether a real Qwen answers the prompts usefully is a separate question,
answered by running against an actual model, not by a test.
"""

import pytest

from src.agents import AgentMode, GraphConfig, build_graph, run_pipeline
from src.llm import (
    LLMClient,
    ScriptedBackend,
    extract_json,
    model_fingerprint,
)
from src.loading import load_canonical
from src.trend import Criteria


# ------------------------------------------------------------ JSON parsing

@pytest.mark.parametrize("text,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('```\n{"a": 1}\n```', {"a": 1}),
    ('Sure! Here it is: {"a": 1} Hope that helps.', {"a": 1}),
    ('{"a": 1}\n\nLet me know if you need more.', {"a": 1}),
    ('{"nested": {"b": 2}}', {"nested": {"b": 2}}),
])
def test_extract_json_recovers_real_model_formatting(text, expected):
    assert extract_json(text) == expected


@pytest.mark.parametrize("text", [
    "", "   ", "I cannot help with that.", "!!!", "[1, 2, 3]", '{"a": 1',
])
def test_extract_json_refuses_rather_than_guesses(text):
    assert extract_json(text) is None


# ------------------------------------------------------- client behaviour

def _client(routes, **kw):
    return LLMClient(backend=ScriptedBackend(routes), cache_path=None,
                     model="test-model", **kw)


def test_valid_reply_is_returned_without_fallback():
    client = _client({"PING": '{"ok": true}'})
    value, used_fallback = client.ask_json("PING", seed=1, fallback={"ok": False})
    assert value == {"ok": True}
    assert used_fallback is False
    assert client.stats.fallbacks == 0


def test_unparseable_reply_retries_then_falls_back_and_is_counted():
    client = _client({"PING": "I refuse."}, max_attempts=3)
    value, used_fallback = client.ask_json("PING", seed=1, fallback={"ok": False})
    assert value == {"ok": False}
    assert used_fallback is True
    assert client.stats.parse_retries == 3
    assert client.stats.fallbacks == 1
    assert client.stats.fallback_rate == 1.0


def test_validator_rejects_wrong_shaped_json():
    """Parseable but semantically wrong must also fall back, not pass."""
    client = _client({"PING": '{"unexpected": 1}'}, max_attempts=2)
    value, used_fallback = client.ask_json(
        "PING", seed=1, fallback={"mode": "default"},
        validate=lambda d: "mode" in d,
    )
    assert used_fallback is True
    assert value == {"mode": "default"}


def test_retry_rerolls_the_seed_instead_of_replaying():
    """A retry that reused the seed would deterministically repeat the same
    bad reply, making max_attempts pointless."""
    backend = ScriptedBackend({"PING": "nope"})
    client = LLMClient(backend=backend, cache_path=None, max_attempts=3)
    client.ask_json("PING", seed=5, fallback={})
    seeds = [seed for _, seed in backend.calls]
    assert len(seeds) == 3
    assert len(set(seeds)) == 3, f"seed was not re-rolled: {seeds}"


def test_same_prompt_and_seed_hits_the_cache():
    backend = ScriptedBackend({"PING": '{"ok": true}'})
    client = LLMClient(backend=backend, cache_path=None)
    client.ask_json("PING", seed=1, fallback={})
    client.ask_json("PING", seed=1, fallback={})
    assert len(backend.calls) == 1, "second identical call re-inferred"
    assert client.stats.cache_hits == 1


def test_different_seeds_do_not_share_cache_entries():
    backend = ScriptedBackend({"PING": '{"ok": true}'})
    client = LLMClient(backend=backend, cache_path=None)
    client.ask_json("PING", seed=1, fallback={})
    client.ask_json("PING", seed=2, fallback={})
    assert len(backend.calls) == 2


def test_cache_round_trips_through_disk(tmp_path):
    path = tmp_path / "cache.json"
    backend = ScriptedBackend({"PING": '{"ok": true}'})
    first = LLMClient(backend=backend, cache_path=path)
    first.ask_json("PING", seed=1, fallback={})
    first.flush_cache()

    reloaded = LLMClient(backend=ScriptedBackend({}), cache_path=path)
    value, used_fallback = reloaded.ask_json("PING", seed=1, fallback={"ok": False})
    assert value == {"ok": True} and used_fallback is False


def test_text_reply_falls_back_on_empty():
    client = _client({"PING": "   "})
    assert client.ask_text("PING", seed=1, fallback="default") == "default"
    assert client.stats.fallbacks == 1


def test_stats_are_reportable():
    client = _client({"PING": "nope"}, max_attempts=2)
    client.ask_json("PING", seed=1, fallback={})
    stats = client.stats.as_dict()
    assert stats["llm_calls"] == 1
    assert stats["llm_fallbacks"] == 1
    assert stats["llm_fallback_rate"] == 1.0


def test_model_fingerprint_records_identity():
    fp = model_fingerprint("qwen2.5:3b", ScriptedBackend({}))
    assert fp["model"] == "qwen2.5:3b" and fp["backend"] == "scripted"
    assert len(fp["model_name_sha256"]) == 16
    # No model is behind a scripted backend, so no digest is claimed.
    assert fp["model_digest"] == "unavailable"


def test_unreachable_ollama_reports_no_digest_rather_than_a_guess():
    from src.llm import OllamaBackend
    fp = model_fingerprint("qwen2.5:3b",
                           OllamaBackend(host="http://127.0.0.1:9", timeout=1))
    assert fp["model_digest"] == "unavailable"


# ------------------------------------------------- graph wiring, LLM mode

SCRIPTED_ROUTES = {
    "Decide how the search should be run":
        '{"query_mode": "EXACT_LOCALITY", "reason": "names a locality"}',
    "You review a twelve-month housing price trend":
        '{"suspect_months": ["2023-01", "2023-02"], "reason": "thin months"}',
    "You check property listings for data-entry errors":
        '{"suspect_numbers": []}',
    # Deliberately free of figures: the faithfulness guard rejects any number
    # not present in the run's own facts, and a canned reply cannot know them.
    "Summarise this housing data in two short sentences":
        "Median asking prices per square foot eased slightly across the "
        "reliable months of the window. The figures cover the whole "
        "Hyderabad metro area.",
}


@pytest.fixture(scope="module")
def frame():
    return load_canonical()[0]


def _llm_state(frame, seed=7):
    client = LLMClient(backend=ScriptedBackend(SCRIPTED_ROUTES),
                       cache_path=None, model="scripted")
    config = GraphConfig(agent_mode=AgentMode.LLM)
    return run_pipeline(
        frame,
        Criteria(window_end="2023-08", bhk=(3,), localities=("Gachibowli",),
                 label="llm-test"),
        seed=seed, config=config, graph=build_graph(config.n_retrieval_agents),
        user_query="3 BHK in Gachibowli over the last twelve months",
        llm=client,
    ), client


def test_graph_runs_end_to_end_in_llm_mode(frame):
    state, _ = _llm_state(frame)
    assert state["final_report"] is not None
    assert state["narrative"]


def test_llm_mode_still_fires_both_cycles(frame):
    state, _ = _llm_state(frame)
    assert state["retry_count"] > 0, "cycle 1 did not fire in LLM mode"
    assert state["critique_rounds"] > 0, "cycle 2 did not fire in LLM mode"


def test_criteria_agent_uses_the_models_query_mode(frame):
    state, _ = _llm_state(frame)
    planned = [e for e in state["trace"] if e["agent"] == "CriteriaAgent"][0]
    assert planned["action"] == "planned (LLM)"
    assert planned["query_mode"] == "EXACT_LOCALITY"


def test_critique_agent_adds_the_models_flagged_months(frame):
    """The model contributes on top of the deterministic floor."""
    state, _ = _llm_state(frame)
    assert set(state["flagged_months"]) >= {"2023-01", "2023-02"}


def test_llm_mode_cannot_switch_off_the_deterministic_floor(frame):
    """Regression: validated against qwen2.5:3b, the model returned no suspect
    months, cycle 2 never fired and no contamination was rejected. The
    deterministic checks must run regardless of what the model says."""
    routes = dict(SCRIPTED_ROUTES)
    routes["You review a twelve-month housing price trend"] = \
        '{"suspect_months": [], "reason": "all fine"}'
    client = LLMClient(backend=ScriptedBackend(routes), cache_path=None)
    config = GraphConfig(agent_mode=AgentMode.LLM)
    state = run_pipeline(
        frame,
        Criteria(window_end="2023-08", bhk=(3,), localities=("Gachibowli",),
                 label="floor"),
        seed=7, config=config, graph=build_graph(config.n_retrieval_agents),
        user_query="3 BHK in Gachibowli", llm=client,
    )
    assert state["critique_rounds"] > 0, "cycle 2 went dormant in LLM mode"
    assert state["n_rejected_outliers"] > 0, "contamination went unrejected"


def test_narrative_comes_from_the_model(frame):
    state, _ = _llm_state(frame)
    assert "eased slightly" in state["narrative"]


def test_unfaithful_narrative_is_rejected_and_counted(frame):
    """A summary that invents a figure must not reach the user.

    Measured on a real 0.5B model: given the facts, it reported "12 months of
    reliable listings" when six were reliable, restated a percentage change as
    a price, and copied an instruction line into its output. All three are
    detectable, because every numeric token must come from the supplied facts.
    """
    routes = dict(SCRIPTED_ROUTES)
    routes["Summarise this housing data in two short sentences"] = (
        "Prices rose 99.9% over 37 months across 123456 listings."
    )
    client = LLMClient(backend=ScriptedBackend(routes), cache_path=None)
    config = GraphConfig(agent_mode=AgentMode.LLM)
    state = run_pipeline(
        frame,
        Criteria(window_end="2023-08", bhk=(3,), localities=("Gachibowli",),
                 label="unfaithful"),
        seed=7, config=config, graph=build_graph(config.n_retrieval_agents),
        user_query="3 BHK in Gachibowli", llm=client,
    )
    assert "99.9%" not in state["narrative"]
    assert "Hyderabad asking-price trend" in state["narrative"], (
        "should have fallen back to the deterministic template"
    )
    assert any(e.get("narrative_rejected") for e in state["trace"])
    assert client.stats.fallbacks >= 1, "rejection was not counted"


def test_narrative_guard_rejects_leaked_instructions():
    """Measured against both qwen2.5:0.5b and :3b -- small models echo the
    instruction lines back, which must never reach a user."""
    from src.agents.nodes import _narrative_is_faithful
    ok, why = _narrative_is_faithful(
        "area covered: the whole metro. Output nothing but the two sentences.",
        {"12"})
    assert not ok and "leaked" in why


def test_narrative_guard_rejects_invented_figures():
    from src.agents.nodes import _narrative_is_faithful
    ok, why = _narrative_is_faithful("Prices rose 99.9% over 37 months.", {"12"})
    assert not ok and "invented" in why


def test_narrative_guard_accepts_supplied_figures():
    from src.agents.nodes import _narrative_is_faithful
    ok, why = _narrative_is_faithful(
        "The median moved 13.6% across 6 of 12 months, over 4142 listings.",
        {"12", "6", "4142", "13.6"})
    assert ok, why


def test_llm_stats_reach_the_report_provenance(frame):
    state, client = _llm_state(frame)
    provenance = state["final_report"].provenance
    assert provenance["agent_mode"] == "LLM"
    assert provenance["llm_calls"] == client.stats.calls
    assert "llm_fallback_rate" in provenance


def test_statistics_are_identical_in_both_modes(frame):
    """The model supplies judgment, never arithmetic. With the critique agent
    scripted to flag the same months the deterministic rule finds, the two
    modes must agree exactly -- any difference would mean the LLM had leaked
    into the statistics."""
    routes = dict(SCRIPTED_ROUTES)
    routes["You review a twelve-month housing price trend"] = \
        '{"suspect_months": [], "reason": "looks fine"}'
    client = LLMClient(backend=ScriptedBackend(routes), cache_path=None)
    config = GraphConfig(agent_mode=AgentMode.LLM, max_critique_rounds=0)
    criteria = Criteria(window_end="2023-08", label="parity")

    llm_state = run_pipeline(frame, criteria, seed=3, config=config,
                             graph=build_graph(), user_query="all listings",
                             llm=client)
    det_state = run_pipeline(frame, criteria, seed=3,
                             config=GraphConfig(max_critique_rounds=0),
                             graph=build_graph())
    assert (llm_state["final_report"].psf_series()
            == det_state["final_report"].psf_series())
    assert (llm_state["final_report"].count_series()
            == det_state["final_report"].count_series())


# ============================================================================
# Prompt invariance
# ============================================================================
#
# The Kaggle sweep (results/llm/) found that LLM mode broke three relations
# that hold deterministically: relabelling listing ids violated 0.630,
# duplication 0.417, and a display-unit change 0.028. Cycle 2 fired in 100% of
# runs with round counts never differing, so the cause was not *whether* the
# model was consulted but *what it was shown*.
#
# The determinism probe on the Kaggle GPU returned 20/20 identical replies at
# temperature 0 with a fixed seed. Given that, these tests are stronger than
# sampling a model would be: if the prompt is byte-identical between the
# source and follow-up runs, a deterministic model must answer identically,
# so the relation holds by construction rather than by observation.

#: Prompts whose answers decide WHICH listings are counted. The narrative is
#: excluded on purpose: it is written after every statistic is final and
#: influences no selection, and it legitimately differs between runs -- under
#: duplication it must report twice as many listings, which is exactly what
#: the duplication relation requires.
SELECTION_PROMPT_MARKERS = (
    "You plan property searches",                      # Criteria agent
    "data-entry errors",                               # Analysis review
    "twelve-month housing price trend",                # Critique agent
)


def _captured_prompts(frame, criteria, seed=11, user_query="all listings",
                      selection_only=True):
    """Run the pipeline in LLM mode and return the prompts it issued."""
    backend = ScriptedBackend(SCRIPTED_ROUTES)
    client = LLMClient(backend=backend, cache_path=None, model="scripted")
    config = GraphConfig(agent_mode=AgentMode.LLM)
    run_pipeline(frame, criteria, seed=seed, config=config,
                 graph=build_graph(config.n_retrieval_agents),
                 user_query=user_query, llm=client)
    prompts = [prompt for prompt, _ in backend.calls]
    if not selection_only:
        return prompts
    return [p for p in prompts
            if any(m in p for m in SELECTION_PROMPT_MARKERS)]


def _prompt_pair(frame, mr_id, criteria):
    """Prompts from the source run and from the relation's follow-up run."""
    import numpy as np
    from src.mr.relations import BY_ID
    mr = BY_ID[mr_id]
    prepared = mr.prepare(criteria)
    follow_frame, follow_criteria = mr.transform(
        frame, prepared, np.random.default_rng(11)
    )
    return (_captured_prompts(frame, prepared),
            _captured_prompts(follow_frame, follow_criteria))


def _base_input(frame):
    """A representative base input -- one the sweep actually measures.

    Not a hand-written Criteria: the generated inputs all carry a price band
    AND a locality list, so cycle 1 exhausts its levers identically in both
    runs. An input with a thin lever profile diverges on the relaxation path
    instead, which is a separate, already-documented effect (the coverage
    feedback loop) and would mask the prompt-content question these tests
    exist to ask.
    """
    global _BASE_INPUT
    if _BASE_INPUT is None:
        from src.mr.base_inputs import generate_base_inputs
        # The first generated input whose run actually issues a grey-zone
        # review prompt. Since geography widening keeps the locality
        # constraint (contracts/Coverage.md §3), input 0 no longer does, and
        # the prompt-invariance tests would otherwise pass vacuously.
        for candidate in generate_base_inputs(frame):
            if any("data-entry errors" in p
                   for p in _captured_prompts(frame, candidate)):
                _BASE_INPUT = candidate
                break
        assert _BASE_INPUT is not None, "no base input issues a review prompt"
    return _BASE_INPUT


_BASE_INPUT = None


def test_relabelling_ids_leaves_every_prompt_unchanged(frame):
    """MR-I4 violated 0.630 on Kaggle because the review prompt carried
    listing ids, so a bijective relabelling changed the text the model saw."""
    source, follow = _prompt_pair(frame, "I4", _base_input(frame))
    assert source == follow, (
        "relabelling ids changed a prompt; the model's judgment can therefore "
        "depend on an identifier that carries no information about whether a "
        "listing's description corroborates its price"
    )


def test_display_units_leave_every_prompt_unchanged(frame):
    """MR-I2 violated 0.028 on Kaggle because the critique table was rendered
    in display units, so re-expressing the report in lakh per square metre
    changed which months the model called anomalous."""
    source, follow = _prompt_pair(frame, "I2", _base_input(frame))
    assert source == follow, (
        "a display-unit change altered a prompt; a judgment about whether a "
        "month looks anomalous must not depend on the units it is shown in"
    )


def test_reordering_rows_leaves_every_prompt_unchanged(frame):
    """MR-I1 already held at 0.000; this pins the reason so a future change
    to prompt construction cannot silently reintroduce order dependence."""
    source, follow = _prompt_pair(frame, "I1", _base_input(frame))
    assert source == follow


def test_currency_projection_leaves_every_prompt_unchanged(frame):
    """MR-I5 (lakh to crore) held at 0.000 for the same reason as I1."""
    source, follow = _prompt_pair(frame, "I5", _base_input(frame))
    assert source == follow


def test_review_prompt_contains_no_listing_identifiers(frame):
    """Positional, not identifier-based. Checked directly as well as through
    the invariance tests, because the invariance could also be satisfied by
    accident if no review were issued at all."""
    prompts = _captured_prompts(frame, _base_input(frame))
    reviews = [p for p in prompts if "data-entry errors" in p]
    assert reviews, "no review prompt was issued; the invariance tests above "\
                    "would then pass vacuously"
    for prompt in reviews:
        assert "id=" not in prompt
        assert "suspect_numbers" in prompt


def test_scaling_prices_does_change_the_prompt(frame):
    """The honest counterpart: MR-D2 violated 0.556 and is NOT fixable by
    prompt hygiene. Scaling every price genuinely changes the figures the
    model is shown, so a different judgment is legitimate. This test records
    that the remaining violation has a different cause from I3/I4."""
    source, follow = _prompt_pair(frame, "D2", _base_input(frame))
    assert source != follow, (
        "scaling prices left the prompts identical, which would mean the "
        "review is not actually seeing prices"
    )


def test_duplication_leaves_every_prompt_unchanged(frame):
    """MR-I3 violated 0.417 on Kaggle. Two causes, both now closed: listing
    ids in the review prompt, and listing counts in the critique table --
    duplication doubles every count, so a count-aware judge flagged different
    months and the medians moved, which is precisely what the relation
    forbids."""
    source, follow = _prompt_pair(frame, "I3", _base_input(frame))
    assert source == follow, (
        "duplicating the dataset changed a prompt; medians cannot then be "
        "invariant under duplication"
    )


def test_critique_prompt_withholds_listing_counts(frame):
    """Checked directly, since the invariance above could also be satisfied
    by the critique never being issued."""
    prompts = _captured_prompts(frame, _base_input(frame))
    critiques = [p for p in prompts if "twelve-month housing price trend" in p]
    assert critiques, "no critique prompt was issued"
    for prompt in critiques:
        # "n=" alone would match inside "media[n=]".
        assert "  n=" not in prompt and "n_active" not in prompt
        assert "median=" in prompt


@pytest.mark.xfail(
    reason="Known, localised, not fully isolated. The duplication relation fell "
           "from 0.417 to 0.176 after the content-addressing fix. Over all 36 "
           "base inputs x 3 seeds, a differing review prompt is NECESSARY but "
           "not sufficient: 0 of the 51 identical-prompt cells violated, while "
           "19 of the 57 differing-prompt cells did. 11 of 36 base inputs "
           "violated on the shipped Kaggle sweep -- base22/23/30/31 on all "
           "three seeds, base11/17/24/27/32/33/35 on one of three. The review "
           "batch comes out with fewer listings on the doubled frame; which "
           "perturbations bite is not isolated. The three inputs asserted below "
           "are drawn from the always-failing group. Open defect, not papered "
           "over. Evidence: results/diagnosis/i3_prompt_vs_violation.csv",
    strict=True,
)
def test_duplication_invariance_residual_on_specific_inputs(frame):
    """The 0.176 residual on MR-I3, pinned so it cannot regress unnoticed."""
    from src.mr.base_inputs import generate_base_inputs
    from src.mr.relations import BY_ID
    import numpy as np
    inputs = {c.label: c for c in generate_base_inputs(frame)}
    mr = BY_ID["I3"]
    for label in ("base22", "base23", "base30"):
        prepared = mr.prepare(inputs[label])
        follow_frame, follow_criteria = mr.transform(
            frame, prepared, np.random.default_rng(11)
        )
        assert (_captured_prompts(frame, prepared)
                == _captured_prompts(follow_frame, follow_criteria)), label


def test_model_radius_without_a_centre_falls_back_to_exact_matching(frame):
    """contracts/Criteria.md §5: the agent never invents a centre for a
    radius search the model asked for."""
    routes = dict(SCRIPTED_ROUTES)
    routes["Decide how the search should be run"] = (
        '{"query_mode": "RADIUS", "reason": "says near"}')
    client = LLMClient(backend=ScriptedBackend(routes), cache_path=None,
                       model="scripted")
    config = GraphConfig(agent_mode=AgentMode.LLM)
    state = run_pipeline(
        frame, Criteria(window_end="2023-08", localities=("Gachibowli",)),
        seed=7, config=config, graph=build_graph(config.n_retrieval_agents),
        user_query="flats near Gachibowli", llm=client,
    )
    planned = [e for e in state["trace"] if e["agent"] == "CriteriaAgent"][0]
    assert planned["query_mode"] == "EXACT_LOCALITY"
    assert "no centre supplied" in planned["reason"]
    assert state["query_mode"] == "EXACT_LOCALITY"
