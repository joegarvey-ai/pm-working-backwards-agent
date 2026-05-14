"""Model routing and orchestration layer.

Provides tiered LLM selection so that high-stakes creative tasks
(research synthesis, PRFAQ writing) use Opus, structural tasks
(BRD, build spec) use Sonnet, and mechanical tasks (validation,
verification) use Haiku.

Also provides retry logic for transient Bedrock errors (toolResult
interleaving race condition in parallel async tasks).

This module is additive: existing code paths work unchanged when
MODEL_ROUTING_ENABLED is unset or false. Enable routing by setting
MODEL_ROUTING_ENABLED=true in .env.

Model tier assignments are configured via AGENT_MODEL_TIER_* env vars
or the default mapping below.
"""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any


class ModelTier(StrEnum):
    """Model capability tiers for routing decisions."""

    opus = "opus"
    sonnet = "sonnet"
    haiku = "haiku"


# Default tier assignments by agent role substring.
# Checked in order; first match wins.
_DEFAULT_TIER_MAP: list[tuple[str, ModelTier]] = [
    ("external_research", ModelTier.sonnet),
    ("customer_evidence", ModelTier.sonnet),
    ("research_agent", ModelTier.opus),
    ("prfaq", ModelTier.opus),
    ("design_brief", ModelTier.sonnet),
    ("brd_cost_risk", ModelTier.sonnet),
    ("brd_compliance", ModelTier.sonnet),
    ("brd_assembly", ModelTier.sonnet),
    ("brd_agent", ModelTier.sonnet),
    ("feedback_classifier", ModelTier.haiku),
]

# Bedrock model IDs per tier.
_BEDROCK_MODELS: dict[ModelTier, str] = {
    ModelTier.opus: os.getenv("BEDROCK_MODEL_OPUS", "us.anthropic.claude-opus-4-6-v1"),
    ModelTier.sonnet: os.getenv("BEDROCK_MODEL_SONNET", "us.anthropic.claude-sonnet-4-6"),
    ModelTier.haiku: os.getenv("BEDROCK_MODEL_HAIKU", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
}

# Direct Anthropic API model IDs per tier.
_ANTHROPIC_MODELS: dict[ModelTier, str] = {
    ModelTier.opus: os.getenv("ANTHROPIC_MODEL_OPUS", "claude-opus-4-0-20250514"),
    ModelTier.sonnet: os.getenv("ANTHROPIC_MODEL_SONNET", "claude-sonnet-4-20250514"),
    ModelTier.haiku: os.getenv("ANTHROPIC_MODEL_HAIKU", "claude-haiku-4-5-20251001"),
}


def is_routing_enabled() -> bool:
    """True when model routing is active."""
    return os.getenv("MODEL_ROUTING_ENABLED", "").strip().lower() in ("true", "1", "yes")


def get_tier_for_agent(agent_key: str) -> ModelTier:
    """Determine the model tier for an agent based on its key/role.

    Checks AGENT_MODEL_TIER_<KEY> env var first (e.g.,
    AGENT_MODEL_TIER_PRFAQ=opus), then falls back to the default map.
    """
    env_key = f"AGENT_MODEL_TIER_{agent_key.upper()}"
    env_val = os.getenv(env_key, "").strip().lower()
    if env_val in ("opus", "sonnet", "haiku"):
        return ModelTier(env_val)

    agent_lower = agent_key.lower()
    for pattern, tier in _DEFAULT_TIER_MAP:
        if pattern in agent_lower:
            return tier

    return ModelTier.sonnet


def get_model_id(tier: ModelTier, provider: str = "") -> str:
    """Return the model ID for the given tier and provider.

    Args:
        tier: The model capability tier.
        provider: "bedrock" or "anthropic". Defaults to LLM_PROVIDER env var.
    """
    if not provider:
        provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

    if provider == "bedrock":
        return _BEDROCK_MODELS[tier]
    return _ANTHROPIC_MODELS[tier]


def routed_llm(agent_key: str, max_tokens: int = 8192) -> Any:
    """Return an LLM instance routed to the appropriate tier for this agent.

    When MODEL_ROUTING_ENABLED is false, returns the default Sonnet LLM
    (same behavior as the existing _llm() factory).

    When enabled, selects the model tier based on the agent key and
    returns the corresponding LLM instance.
    """
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

    if not is_routing_enabled():
        tier = ModelTier.sonnet
    else:
        tier = get_tier_for_agent(agent_key)

    model_id = get_model_id(tier, provider)

    if provider == "bedrock":
        from crewai.llms.providers.bedrock.completion import BedrockCompletion

        return BedrockCompletion(
            model=model_id,
            max_tokens=max_tokens,
            region_name=os.getenv("AWS_BEDROCK_REGION")
            or os.getenv("AWS_REGION", "us-east-2"),
            stream=False,
        )

    from crewai.llms.providers.anthropic.completion import AnthropicCompletion

    return AnthropicCompletion(model=model_id, max_tokens=max_tokens)


# ---------------------------------------------------------------------------
# Retry logic for transient Bedrock errors
# ---------------------------------------------------------------------------

_RETRYABLE_ERRORS = (
    "Expected toolResult blocks",
    "toolResult",
    "Request validation failed",
)

_MAX_RETRIES = int(os.getenv("CREW_MAX_RETRIES", "3"))


def run_crew_with_retry(
    crew_factory: Any,
    inputs: dict[str, Any],
    max_retries: int = _MAX_RETRIES,
    on_retry: Any | None = None,
) -> Any:
    """Execute a crew with retry on known transient Bedrock errors.

    Args:
        crew_factory: A callable that returns a fresh Crew instance.
            Must be a factory (not a pre-built crew) because CrewAI
            mutates agent/task state during execution.
        inputs: The inputs dict passed to crew.kickoff().
        max_retries: Maximum number of retry attempts.
        on_retry: Optional callback(attempt, error) called before each retry.

    Returns:
        The CrewOutput from a successful run.

    Raises:
        The last exception if all retries are exhausted.
    """
    import logging
    import time

    logger = logging.getLogger(__name__)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            crew = crew_factory()
            for t in getattr(crew, "tasks", []):
                t.human_input = False
            return crew.kickoff(inputs=inputs)
        except (ValueError, RuntimeError) as exc:
            error_str = str(exc)
            if not any(pattern in error_str for pattern in _RETRYABLE_ERRORS):
                raise
            last_error = exc
            if on_retry:
                on_retry(attempt, exc)
            logger.warning(
                "Transient Bedrock error on attempt %d/%d: %s",
                attempt,
                max_retries,
                error_str[:150],
            )
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    assert last_error is not None
    raise last_error
