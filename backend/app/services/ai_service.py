"""
FlowList AI service — task parsing and estimation via Anthropic Claude.

Architecture:
  - Prompt templates live in backend/prompts/*.md and are loaded once at import.
    Edit them to tune AI behaviour without touching Python code.
  - _build_prompt()        pure function, fully testable
  - compute_accuracy_bias() pure function, fully testable
  - _call_claude()          async; wraps API with forced tool-use for reliable JSON
  - parse_task_input()      async orchestrator — callers pass pre-fetched history
  - record_task_completion() async; persists actual duration for the feedback loop

Forced tool-use (tool_choice={"type":"tool","name":"..."}) guarantees Claude
always returns the exact JSON schema we need — no brittle text parsing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai_estimation_log import AIEstimationLog

log = logging.getLogger(__name__)

# ── Prompt template loader ────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def _load_template(name: str) -> str:
    """Load a prompt template file. Cached in module-level dict after first read."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


# Load once at import so file-not-found errors surface immediately at startup
_TMPL_PARSE = _load_template("task_parse.md")
_TMPL_CALIBRATION = _load_template("calibration_context.md")
_TMPL_USER_ESTIMATE = _load_template("user_estimate_hint.md")

# ── Claude tool definition ────────────────────────────────────────────────────
# Forced tool-use means Claude MUST respond in this exact schema.

_TASK_PARSE_TOOL: dict = {
    "name": "submit_task_suggestion",
    "description": (
        "Submit a structured task suggestion parsed from the user's "
        "natural language input."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Task title, cleaned and title-cased, max 80 characters.",
            },
            "type": {
                "type": "string",
                "enum": ["work", "personal"],
            },
            "estimated_duration_minutes": {
                "type": "integer",
                "minimum": 15,
                "maximum": 480,
                "description": "Duration estimate in minutes, rounded to nearest 15.",
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "One-sentence explanation of the type / priority / duration "
                    "estimates shown to the user."
                ),
            },
            "optional_deadline_detected": {
                "type": ["string", "null"],
                "description": "ISO date YYYY-MM-DD if a deadline was mentioned, else null.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3–7 lowercase keywords describing the task domain.",
                "minItems": 1,
                "maxItems": 10,
            },
        },
        "required": [
            "title",
            "type",
            "estimated_duration_minutes",
            "reasoning",
            "confidence",
            "keywords",
        ],
    },
}

# ── Schemas (also exported; imported by router and tests) ─────────────────────


class AISuggestion(BaseModel):
    title: str
    type: Literal["work", "personal"]
    estimated_duration_minutes: int = Field(ge=15, le=480)
    reasoning: str
    optional_deadline_detected: date | None = None
    confidence: Literal["high", "medium", "low"]
    keywords: list[str] = Field(default_factory=list)


class ParseRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=2000)
    optional_user_estimate: str | None = None


class ParseResponse(BaseModel):
    suggestion: AISuggestion
    ai_available: bool


# ── Pure helpers ──────────────────────────────────────────────────────────────


def compute_accuracy_bias(
    history: list[AIEstimationLog],
) -> dict | None:
    """
    Analyse estimation history and return a bias correction dict, or None if
    there aren't enough samples or the bias isn't significant.

    Returns:
        {
            "sample_size": int,
            "avg_error_pct": float,   # positive = AI underestimates (actual > estimated)
            "avg_error_pct_abs": float,
            "direction": "underestimate" | "overestimate",
            "suggested_multiplier": float,
            "example_corrected": int,  # what 60 min becomes after correction
            "task_type": str,
        }
    """
    samples = [
        e for e in history
        if e.actual_minutes is not None and e.estimated_minutes and e.estimated_minutes > 0
    ]
    if len(samples) < 3:
        return None

    error_fractions = [
        (e.actual_minutes - e.estimated_minutes) / e.estimated_minutes
        for e in samples
    ]
    avg_error_pct = (sum(error_fractions) / len(error_fractions)) * 100

    # Only report bias if it is meaningful (> 15% either direction)
    if abs(avg_error_pct) < 15.0:
        return None

    direction = "underestimate" if avg_error_pct > 0 else "overestimate"
    multiplier = round(1.0 + (avg_error_pct / 100), 2)
    # Clamp to a sane range — don't let one outlier-heavy sample go wild
    multiplier = max(0.5, min(multiplier, 2.5))

    task_type = samples[0].task_type if samples else "work"

    return {
        "sample_size": len(samples),
        "avg_error_pct": round(avg_error_pct, 1),
        "avg_error_pct_abs": round(abs(avg_error_pct), 1),
        "direction": direction,
        "suggested_multiplier": multiplier,
        "example_corrected": round(60 * multiplier / 15) * 15,  # snap to 15-min grid
        "task_type": task_type,
    }


def _build_prompt(
    raw_text: str,
    user_estimate: str | None,
    bias: dict | None,
    backlog_preview: list[str] | None,
) -> str:
    """
    Build the complete user-turn message for the Claude API call.
    Pure function — no I/O, no side effects. Fully testable.
    """
    # User estimate section
    if user_estimate and user_estimate.strip():
        user_estimate_section = _TMPL_USER_ESTIMATE.format(
            user_estimate=user_estimate.strip()
        )
    else:
        user_estimate_section = ""

    # Calibration section
    if bias:
        calibration_section = _TMPL_CALIBRATION.format(**bias)
    else:
        calibration_section = ""

    # Backlog summary
    if backlog_preview:
        items = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(backlog_preview))
        backlog_section = f"## Current Top Tasks (for priority context)\n{items}"
    else:
        backlog_section = ""

    return _TMPL_PARSE.format(
        raw_text=raw_text.strip(),
        user_estimate_section=user_estimate_section,
        calibration_section=calibration_section,
        backlog_section=backlog_section,
        today=date.today().isoformat(),
    )


def _parse_claude_output(tool_input: dict) -> AISuggestion:
    """
    Coerce Claude's tool-call dict into an AISuggestion.
    Applies light sanitisation: clamp duration, normalise deadline.
    """
    deadline_raw = tool_input.get("optional_deadline_detected")
    deadline: date | None = None
    if deadline_raw:
        try:
            deadline = date.fromisoformat(str(deadline_raw))
        except ValueError:
            deadline = None

    duration = int(tool_input.get("estimated_duration_minutes", 60))
    # Snap to nearest 15 minutes and clamp
    duration = max(15, min(480, round(duration / 15) * 15))

    return AISuggestion(
        title=str(tool_input.get("title", "")).strip()[:512] or "New Task",
        type=tool_input.get("type", "work"),
        estimated_duration_minutes=duration,
        reasoning=str(tool_input.get("reasoning", "")).strip(),
        optional_deadline_detected=deadline,
        confidence=tool_input.get("confidence", "medium"),
        keywords=list(tool_input.get("keywords", [])),
    )


def _build_fallback(raw_text: str) -> ParseResponse:
    """
    Returned when the Claude API is unavailable.
    Provides safe defaults so the user can still create the task manually.
    """
    return ParseResponse(
        suggestion=AISuggestion(
            title=raw_text.strip()[:512] or "New Task",
            type="work",
            estimated_duration_minutes=60,
            reasoning="AI is temporarily unavailable. Please fill in the details below.",
            optional_deadline_detected=None,
            confidence="low",
            keywords=[],
        ),
        ai_available=False,
    )


# ── Claude API call ───────────────────────────────────────────────────────────


async def _call_claude(prompt: str) -> dict:
    """
    Call Claude with forced tool-use. Returns the raw tool-call input dict.
    Raises anthropic.APIError subclasses on failure — callers handle graceful degradation.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        tools=[_TASK_PARSE_TOOL],
        tool_choice={"type": "tool", "name": "submit_task_suggestion"},
        messages=[{"role": "user", "content": prompt}],
    )
    tool_block = next(
        (b for b in response.content if b.type == "tool_use"), None
    )
    if tool_block is None:
        raise ValueError("Claude response contained no tool_use block")
    return tool_block.input


# ── Public API ────────────────────────────────────────────────────────────────


async def parse_task_input(
    raw_text: str,
    user_estimate: str | None = None,
    history: list[AIEstimationLog] | None = None,
    backlog_preview: list[str] | None = None,
) -> ParseResponse:
    """
    Parse a natural-language task string using Claude.

    Args:
        raw_text:        The user's raw task description.
        user_estimate:   Optional time estimate provided by the user in hours
                         (e.g. "0.5", "1", "1.5", "2"). Already formatted as
                         "{value} hours" by the caller before passing here.
        history:         Recent AIEstimationLog rows for the same task type,
                         used to calibrate the estimate. Fetch with
                         ai_log_repo.get_recent_by_type() before calling.
        backlog_preview: Titles of the top N current tasks for priority context.

    Returns:
        ParseResponse with suggestion + ai_available flag.
        On API failure, returns a safe fallback (ai_available=False).
    """
    bias = compute_accuracy_bias(history or [])
    prompt = _build_prompt(raw_text, user_estimate, bias, backlog_preview)

    try:
        tool_input = await _call_claude(prompt)
        suggestion = _parse_claude_output(tool_input)
        return ParseResponse(suggestion=suggestion, ai_available=True)

    except anthropic.APIConnectionError as exc:
        log.warning("Claude API connection error: %s", exc)
        return _build_fallback(raw_text)

    except anthropic.APIStatusError as exc:
        log.warning("Claude API status error %s: %s", exc.status_code, exc.message)
        return _build_fallback(raw_text)

    except anthropic.APITimeoutError as exc:
        log.warning("Claude API timeout: %s", exc)
        return _build_fallback(raw_text)

    except Exception as exc:
        # Catch-all: unexpected parse errors, etc. Always degrade gracefully.
        log.exception("Unexpected error in parse_task_input: %s", exc)
        return _build_fallback(raw_text)


async def record_task_completion(
    db: AsyncSession,
    task_id: int,
    actual_minutes: int,
) -> None:
    """
    Persist the actual task duration when a task is marked done.
    Updates the ai_estimation_log row for this task so the feedback loop
    has accurate data for future calibration.
    """
    from app.repositories import ai_log_repo
    await ai_log_repo.record_actual(db, task_id, actual_minutes)
