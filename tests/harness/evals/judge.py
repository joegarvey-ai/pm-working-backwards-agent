"""LLM-as-judge evaluations for subjective quality scoring.

Each judge function accepts a RunRecord, calls Claude Haiku to score
the relevant output against a rubric, and returns structured results.
Judge results can be stored in the RunRecord for trend tracking. Haiku
keeps judge cost well under production cost, per the harness roadmap.

Provider routing:
  - Default: direct Anthropic API (LLM_PROVIDER unset or "anthropic",
    uses ANTHROPIC_API_KEY), matching the production pipeline default.
  - Alternative: AWS Bedrock (set LLM_PROVIDER=bedrock, uses
    AWS_BEARER_TOKEN_BEDROCK / region config).
  - Override judge model via HARNESS_JUDGE_MODEL env var.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from tests.harness.models import RunRecord

_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()

_JUDGE_MODEL_ANTHROPIC = os.getenv("HARNESS_JUDGE_MODEL", "claude-haiku-4-5")
_JUDGE_MODEL_BEDROCK = os.getenv(
    "HARNESS_JUDGE_MODEL",
    os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
)
if _JUDGE_MODEL_BEDROCK and not _JUDGE_MODEL_BEDROCK.startswith(
    ("us.", "global.", "eu.", "apac.")
):
    _JUDGE_MODEL_BEDROCK = f"us.{_JUDGE_MODEL_BEDROCK}"


@dataclass
class CriterionScore:
    criterion: str
    score: int  # 1-5
    rationale: str


@dataclass
class JudgeResult:
    judge_name: str
    scores: list[CriterionScore] = field(default_factory=list)
    overall_score: float = 0.0
    summary: str = ""
    raw_response: str = ""
    # Populated when the judge call or the response parse failed. When set,
    # overall_score is meaningless (do NOT treat 0.0 as a real low score).
    error: str | None = None

    def to_record(self):
        """Convert to a serializable JudgeResultRecord for the RunRecord."""
        from tests.harness.models import CriterionScoreRecord, JudgeResultRecord

        return JudgeResultRecord(
            judge_name=self.judge_name,
            scores=[
                CriterionScoreRecord(
                    criterion=s.criterion, score=s.score, rationale=s.rationale
                )
                for s in self.scores
            ],
            overall_score=self.overall_score,
            summary=self.summary,
            error=self.error,
        )


def _call_judge(system_prompt: str, user_prompt: str) -> str:
    """Call the judge model and return the response text.

    Routes through Bedrock by default (matching production pipeline config).
    Falls back to direct Anthropic API when LLM_PROVIDER=anthropic.
    """
    if _LLM_PROVIDER == "bedrock":
        return _call_judge_bedrock(system_prompt, user_prompt)
    return _call_judge_anthropic(system_prompt, user_prompt)


def _call_judge_bedrock(system_prompt: str, user_prompt: str) -> str:
    """Call judge via AWS Bedrock converse API."""
    import boto3
    from botocore.config import Config

    region = os.getenv("AWS_BEDROCK_REGION") or os.getenv("AWS_REGION", "us-east-2")
    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(read_timeout=120, connect_timeout=10),
    )
    response = client.converse(
        modelId=_JUDGE_MODEL_BEDROCK,
        system=[{"text": system_prompt}],
        messages=[
            {"role": "user", "content": [{"text": user_prompt}]},
        ],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
    )
    return response["output"]["message"]["content"][0]["text"]


def _call_judge_anthropic(system_prompt: str, user_prompt: str) -> str:
    """Call judge via direct Anthropic API."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=_JUDGE_MODEL_ANTHROPIC,
        max_tokens=4096,
        temperature=0.0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _parse_judge_response(raw: str) -> tuple[list[CriterionScore], bool]:
    """Parse a JSON array of criterion scores from the judge response.

    Returns ``(scores, parse_ok)``. ``parse_ok`` is False when no JSON
    array could be found or it failed to parse, which lets callers
    distinguish a parse failure from a genuine empty/low score.
    """
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        return [], False
    try:
        items = json.loads(raw[start:end])
        scores = [
            CriterionScore(
                criterion=item["criterion"],
                score=int(item["score"]),
                rationale=item["rationale"],
            )
            for item in items
        ]
        return scores, True
    except (json.JSONDecodeError, KeyError, ValueError):
        return [], False


def _score(judge_name: str, system_prompt: str, user_prompt: str) -> JudgeResult:
    """Call the judge, parse the response, and build a JudgeResult.

    Sets ``error`` (leaving overall_score at 0.0 as a non-signal) when the
    call raises or the response cannot be parsed, so a broken judge is
    never mistaken for a real low score.
    """
    try:
        raw = _call_judge(system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001 — surface call failure, don't crash the run
        return JudgeResult(
            judge_name=judge_name,
            summary=f"Judge call failed: {exc}",
            error=f"call_failed: {exc}",
        )

    scores, parse_ok = _parse_judge_response(raw)
    if not parse_ok:
        return JudgeResult(
            judge_name=judge_name,
            summary="Judge response could not be parsed as scores.",
            raw_response=raw,
            error="parse_failed",
        )

    overall = sum(s.score for s in scores) / len(scores) if scores else 0.0
    return JudgeResult(
        judge_name=judge_name,
        scores=scores,
        overall_score=overall,
        summary=f"{judge_name}: {overall:.1f}/5 across {len(scores)} criteria",
        raw_response=raw,
    )


def _find_output(record: RunRecord, task_substring: str) -> str | None:
    """Find the first agent output whose task name contains the substring."""
    for name, output in record.agent_outputs.items():
        if task_substring in name.lower():
            return output
    return None


# ---------------------------------------------------------------------------
# Judge: PRFAQ Working Backwards Fidelity
# ---------------------------------------------------------------------------

_PRFAQ_FIDELITY_SYSTEM = """You are a senior Amazon PM reviewing a PRFAQ for Working Backwards style fidelity.

Score each criterion 1-5 where:
  1 = Completely fails the criterion
  2 = Mostly fails with some elements present
  3 = Partially meets, notable gaps
  4 = Mostly meets with minor issues
  5 = Fully meets the criterion

Return your evaluation as a JSON array with this exact structure:
[
  {"criterion": "<name>", "score": <1-5>, "rationale": "<1-2 sentences>"},
  ...
]

Do not include any text outside the JSON array."""

_PRFAQ_FIDELITY_CRITERIA = """Evaluate the PRFAQ against these criteria:

1. "no_em_dashes" - The text does not use em dashes as punctuation. Colons or sentence breaks are used instead.
2. "no_contrast_hooks" - The text avoids rhetorical contrast hooks ("not X, instead Y" as a device). Straightforward claims are used.
3. "inverted_pyramid" - Each section leads with the claim or conclusion, followed by supporting detail. No burying the lead.
4. "one_idea_per_paragraph" - Each paragraph conveys a single idea. No run-on paragraphs mixing multiple concepts.
5. "inline_citations" - Every factual claim traces to a source via inline [source](url) citations or explicit attribution.
"""


def judge_prfaq_fidelity(record: RunRecord) -> JudgeResult:
    """Score PRFAQ output against Working Backwards style rubric.

    Returns a JudgeResult with 5 criterion scores (1-5 each).
    Requires ANTHROPIC_API_KEY to be set.
    """
    prfaq_text = _find_output(record, "prfaq")
    if prfaq_text is None:
        return JudgeResult(
            judge_name="prfaq_fidelity",
            summary="No PRFAQ output found in record",
        )

    user_prompt = f"""{_PRFAQ_FIDELITY_CRITERIA}

Here is the PRFAQ to evaluate:

<prfaq>
{prfaq_text[:30000]}
</prfaq>"""

    return _score("prfaq_fidelity", _PRFAQ_FIDELITY_SYSTEM, user_prompt)


# ---------------------------------------------------------------------------
# Judge: Citation Accuracy
# ---------------------------------------------------------------------------

_CITATION_SYSTEM = """You are a fact-checker reviewing research and PRFAQ outputs for citation accuracy.

For each factual claim you identify, check whether it has an inline citation or source attribution.

Return your evaluation as a JSON array:
[
  {"criterion": "sourced_claims_ratio", "score": <1-5>, "rationale": "<how many claims are sourced vs unsourced>"},
  {"criterion": "citation_validity", "score": <1-5>, "rationale": "<are citations real URLs or plausible sources, not hallucinated>"},
  {"criterion": "claim_support_strength", "score": <1-5>, "rationale": "<do citations actually support the claims they're attached to>"}
]

Scoring:
  1 = <20% of claims cited / mostly hallucinated / citations don't support claims
  2 = 20-40% cited / some hallucinated / weak support
  3 = 40-60% cited / mostly real / moderate support
  4 = 60-80% cited / all real / good support
  5 = >80% cited / all verifiable / strong support

Do not include any text outside the JSON array."""


def judge_citation_accuracy(record: RunRecord) -> JudgeResult:
    """Score citation coverage and accuracy across research and PRFAQ outputs.

    Returns a JudgeResult with 3 criterion scores.
    Requires ANTHROPIC_API_KEY to be set.
    """
    research_text = _find_output(record, "research") or ""
    prfaq_text = _find_output(record, "prfaq") or ""

    combined = research_text[:15000] + "\n\n---\n\n" + prfaq_text[:15000]
    if not combined.strip():
        return JudgeResult(
            judge_name="citation_accuracy",
            summary="No research or PRFAQ output found",
        )

    user_prompt = f"""Review the following research brief and PRFAQ for citation accuracy:

<outputs>
{combined}
</outputs>"""

    return _score("citation_accuracy", _CITATION_SYSTEM, user_prompt)


# ---------------------------------------------------------------------------
# Judge: AWS Alignment
# ---------------------------------------------------------------------------

_AWS_ALIGNMENT_SYSTEM = """You are a technical reviewer checking a BRD for AWS service alignment.

The organization's policy is: default to AWS services for all technical architecture decisions. Non-AWS vendors (Supabase, Firebase, Vercel, Heroku, etc.) should only appear if explicitly requested in the input brief.

Score each criterion 1-5:

Return your evaluation as a JSON array:
[
  {"criterion": "aws_default_services", "score": <1-5>, "rationale": "<does the BRD default to AWS services like Lambda, DynamoDB, Bedrock, S3, etc.>"},
  {"criterion": "no_unauthorized_vendors", "score": <1-5>, "rationale": "<are non-AWS vendors absent or only present when explicitly requested>"},
  {"criterion": "service_specificity", "score": <1-5>, "rationale": "<are specific AWS service names used rather than generic descriptions>"}
]

Scoring:
  1 = Non-AWS vendors dominate / generic descriptions only
  2 = Mix of AWS and non-AWS without justification
  3 = Mostly AWS but some unexplained non-AWS references
  4 = Almost entirely AWS with specific service names
  5 = Fully AWS-aligned with specific services and no unauthorized vendors

Do not include any text outside the JSON array."""


def judge_aws_alignment(record: RunRecord) -> JudgeResult:
    """Score BRD output for AWS service alignment.

    Returns a JudgeResult with 3 criterion scores.
    Requires ANTHROPIC_API_KEY to be set.

    Returns a neutral result if no BRD output is found (research-only runs).
    """
    brd_text = _find_output(record, "brd")
    if brd_text is None:
        return JudgeResult(
            judge_name="aws_alignment",
            summary="No BRD output found in record (expected for research-only runs)",
        )

    user_prompt = f"""Review the following BRD for AWS service alignment:

<brd>
{brd_text[:30000]}
</brd>"""

    return _score("aws_alignment", _AWS_ALIGNMENT_SYSTEM, user_prompt)
