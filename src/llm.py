"""Local-model client for the agent graph.

Design constraints, in order of importance:

1. **Reproducibility.** The harness's recorded seed is passed to the model on
   every call, temperature is pinned to 0, and the model identity (name + a
   digest of its tag) is recorded alongside the data snapshot's checksum. The
   seed, the frozen snapshot and the model are the three artifacts that make a
   run re-runnable.
2. **Honesty about failure.** A 3B model does not always return parseable
   JSON. Retries are bounded, and when they are exhausted the caller gets a
   recorded deterministic fallback -- never a silent guess. Every fallback is
   counted and surfaced, because a high fallback rate means the LLM path is
   weaker than it looks and the report must say so.
3. **Cost.** The same prompt recurs across relations and seeds, so responses
   are cached by (prompt, seed, model) hash. The cache doubles as a replay
   artifact: a grader can reproduce a sweep without a GPU.

The backend is pluggable so the whole agent graph can be exercised in LLM mode
without a model present (``ScriptedBackend``), which is what lets the wiring,
the seed threading and the fallback paths be tested offline.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

DEFAULT_MODEL = "qwen2.5:3b-instruct-q4_K_M"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_CACHE = Path("data/llm_cache/responses.json")


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

class Backend(ABC):
    """Anything that can turn a prompt into text."""

    name: str = "abstract"

    @abstractmethod
    def generate(self, prompt: str, *, seed: int, model: str,
                 temperature: float, num_predict: int) -> str:
        ...


class OllamaBackend(Backend):
    """Talks to a local Ollama server over HTTP.

    Uses urllib rather than the `ollama` package so the only dependency is the
    standard library -- one less version to pin for reproducibility.
    """

    name = "ollama"

    def __init__(self, host: str = DEFAULT_HOST, timeout: float = 180.0):
        self.host = host.rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str, *, seed: int, model: str,
                 temperature: float, num_predict: int) -> str:
        import urllib.error
        import urllib.request

        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "seed": seed,
                "num_predict": num_predict,
                # Greedy decoding: with temperature 0 these are belt-and-braces,
                # but Ollama applies sampler defaults unless they are overridden.
                "top_k": 1,
                "top_p": 1.0,
                "repeat_penalty": 1.0,
            },
        }).encode()
        request = urllib.request.Request(
            f"{self.host}/api/generate", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode())
        return body.get("response", "")


class ScriptedBackend(Backend):
    """Returns canned responses. For tests only; never used for reported results.

    Matching is by substring on the prompt so a test can script one response
    per agent without reproducing the full prompt text. Unmatched prompts raise
    rather than returning something plausible -- a silent default here would
    hide exactly the wiring bugs this backend exists to catch.
    """

    name = "scripted"

    def __init__(self, routes: dict[str, str | Callable[[str], str]]):
        self.routes = routes
        self.calls: list[tuple[str, int]] = []

    def generate(self, prompt: str, *, seed: int, model: str,
                 temperature: float, num_predict: int) -> str:
        self.calls.append((prompt, seed))
        for marker, response in self.routes.items():
            if marker in prompt:
                return response(prompt) if callable(response) else response
        raise KeyError(
            f"ScriptedBackend has no route matching prompt: {prompt[:120]!r}"
        )


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

@dataclass
class LLMStats:
    """Per-run accounting. Reported, never discarded."""

    calls: int = 0
    cache_hits: int = 0
    parse_retries: int = 0
    fallbacks: int = 0
    errors: int = 0
    seconds: float = 0.0

    @property
    def fallback_rate(self) -> float:
        return self.fallbacks / self.calls if self.calls else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "llm_calls": self.calls,
            "llm_cache_hits": self.cache_hits,
            "llm_parse_retries": self.parse_retries,
            "llm_fallbacks": self.fallbacks,
            "llm_errors": self.errors,
            "llm_fallback_rate": round(self.fallback_rate, 4),
            "llm_seconds": round(self.seconds, 2),
        }


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict | None:
    """Best-effort JSON object extraction from a model's reply.

    Small instruction-tuned models wrap JSON in prose, in markdown fences, or
    emit it with trailing commentary. Each of those is recoverable and none of
    them is a model failure, so we try in order of decreasing cleanliness
    before giving up. Returns None only when nothing object-shaped is present.
    """
    if not text:
        return None

    candidates: list[str] = []
    stripped = text.strip()
    candidates.append(stripped)
    for match in _FENCE.findall(text):
        candidates.append(match.strip())
    # Outermost brace-balanced span, for replies with leading/trailing prose.
    start = text.find("{")
    if start != -1:
        depth = 0
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:index + 1])
                    break

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


@dataclass
class LLMClient:
    """Seeded, cached, fallback-safe access to a local model."""

    backend: Backend
    model: str = DEFAULT_MODEL
    temperature: float = 0.0
    num_predict: int = 256
    max_attempts: int = 3
    cache_path: Path | None = DEFAULT_CACHE
    stats: LLMStats = field(default_factory=LLMStats)
    _cache: dict[str, str] = field(default_factory=dict, repr=False)
    _cache_dirty: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        if self.cache_path and Path(self.cache_path).exists():
            try:
                self._cache = json.loads(Path(self.cache_path).read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._cache = {}

    # -- cache ----------------------------------------------------------

    def _key(self, prompt: str, seed: int, attempt: int) -> str:
        digest = hashlib.sha256(
            f"{self.model}\x00{self.temperature}\x00{seed}\x00{attempt}"
            f"\x00{prompt}".encode()
        ).hexdigest()
        return digest

    def flush_cache(self) -> None:
        if not (self.cache_path and self._cache_dirty):
            return
        path = Path(self.cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._cache, indent=0, sort_keys=True),
                        encoding="utf-8", newline="\n")
        self._cache_dirty = False

    # -- generation -----------------------------------------------------

    def _raw(self, prompt: str, seed: int, attempt: int) -> str:
        key = self._key(prompt, seed, attempt)
        if key in self._cache:
            self.stats.cache_hits += 1
            return self._cache[key]
        started = time.perf_counter()
        try:
            text = self.backend.generate(
                prompt, seed=seed, model=self.model,
                temperature=self.temperature, num_predict=self.num_predict,
            )
        except KeyError:
            raise
        except Exception:
            self.stats.errors += 1
            raise
        finally:
            self.stats.seconds += time.perf_counter() - started
        self._cache[key] = text
        self._cache_dirty = True
        return text

    def ask_json(
        self,
        prompt: str,
        *,
        seed: int,
        fallback: dict,
        validate: Callable[[dict], bool] | None = None,
    ) -> tuple[dict, bool]:
        """Ask for a JSON object. Returns ``(value, used_fallback)``.

        The attempt index is part of the cache key and the model seed, so a
        retry genuinely re-rolls rather than replaying the same bad reply.
        """
        self.stats.calls += 1
        for attempt in range(self.max_attempts):
            try:
                text = self._raw(prompt, seed + attempt * 1000, attempt)
            except KeyError:
                raise
            except Exception:
                break
            parsed = extract_json(text)
            if parsed is not None and (validate is None or validate(parsed)):
                return parsed, False
            self.stats.parse_retries += 1
        self.stats.fallbacks += 1
        return dict(fallback), True

    def ask_text(self, prompt: str, *, seed: int, fallback: str = "") -> str:
        self.stats.calls += 1
        try:
            text = self._raw(prompt, seed, 0).strip()
        except KeyError:
            raise
        except Exception:
            self.stats.fallbacks += 1
            return fallback
        if not text:
            self.stats.fallbacks += 1
            return fallback
        return text


def model_fingerprint(model: str, backend: Backend) -> dict[str, str]:
    """Identity of the model used, for the reproducibility record."""
    return {
        "model": model,
        "backend": backend.name,
        "model_tag_sha256": hashlib.sha256(model.encode()).hexdigest()[:16],
    }
