# FILE MAP
#   14-25  resolve_model: a model spec string -> a Pydantic AI model
#   28-36  model_settings: deterministic decoding for every run
#
# Purpose: one place that maps "ollama:qwen3:8b" or "google:gemini-2.5-flash" to a model, so the
# harness and the CLI take the same --model strings.

from __future__ import annotations

import os

from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

# TWEAK: where Ollama listens (its OpenAI-compatible endpoint)
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")


def resolve_model(spec: str | Model) -> Model | str:
    """`ollama:<tag>` runs locally; any other string is passed to Pydantic AI unchanged."""
    if isinstance(spec, str) and spec.startswith("ollama:"):
        return OllamaModel(spec.removeprefix("ollama:"), provider=OllamaProvider(base_url=OLLAMA_URL))
    return spec


def model_settings() -> ModelSettings:
    # TWEAK: temperature 0 keeps reruns comparable; k>1 samples still differ on API models.
    return ModelSettings(temperature=0.0)


def wants_no_think(spec: str | Model) -> bool:
    """Qwen3 thinks by default, which multiplies output length on these short tasks."""
    return isinstance(spec, str) and "qwen3" in spec.lower()
