"""
Tests for the AI service layer.

Test strategy:
  - Pure functions (compute_accuracy_bias, _build_prompt) → no mocking
  - parse_task_input → mock anthropic.AsyncAnthropic at the class level
  - Graceful degradation → mock raises each API error type

Run: docker compose exec backend pytest tests/test_ai_service.py -v
"""

from __future__ import annotations

import pytest
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.ai_estimation_log import AIEstimationLog
from app.services.ai_service import (
    AISuggestion,
    ParseResponse,
    _build_prompt,
    _parse_claude_output,
    compute_accuracy_bias,
    parse_task_input,
)
import anthropic


# ── Test fixtures ─────────────────────────────────────────────────────────────


def make_log_entry(
    estimated: int,
    actual: int | None,
    task_type: str = "work",
    title: str = "Test task",
) -> AIEstimationLog:
    """Build an AIEstimationLog ORM instance without a real DB session."""
    entry = AIEstimationLog.__new__(AIEstimationLog)
    entry.id = 1
    entry.task_id = 1
    entry.task_type = task_type
    entry.task_title_snapshot = title
    entry.estimated_minutes = estimated
    entry.actual_minutes = actual
    entry.model_used = "claude-test"
    entry.keywords = []
    entry.created_at = datetime.now(tz=timezone.utc)
    entry.updated_at = datetime.now(tz=timezone.utc)
    return entry


def make_claude_response(suggestion: dict[str, Any]) -> MagicMock:
    """
    Build a mock Anthropic API response that looks like a forced tool_use response.
    """
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = suggestion

    response = MagicMock()
    response.content = [tool_block]
    return response


def _mock_claude(suggestion: dict[str, Any]) -> tuple[MagicMock, AsyncMock]:
    """
    Return (mock_cls, mock_instance) ready for use with patch().
    mock_cls is what replaces anthropic.AsyncAnthropic in the module.
    """
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = make_claude_response(suggestion)
    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls, mock_client


_WORK_SUGGESTION = {
    "title": "Review Q2 Board Deck",
    "type": "work",
    "suggested_priority": "top",
    "estimated_duration_minutes": 90,
    "reasoning": "Board deck review is a high-priority focused work task.",
    "optional_deadline_detected": None,
    "confidence": "high",
    "keywords": ["board", "deck", "review", "quarterly"],
}

_PERSONAL_SUGGESTION = {
    "title": "Book Summer Vacation Flights",
    "type": "personal",
    "suggested_priority": "medium",
    "estimated_duration_minutes": 60,
    "reasoning": "Travel planning is a personal task with some time flexibility.",
    "optional_deadline_detected": "2026-05-01",
    "confidence": "high",
    "keywords": ["travel", "vacation", "flights", "booking"],
}


# ── compute_accuracy_bias ─────────────────────────────────────────────────────


class TestComputeAccuracyBias:
    def test_empty_history_returns_none(self):
        assert compute_accuracy_bias([]) is None

    def test_insufficient_samples_returns_none(self):
        history = [make_log_entry(60, 80), make_log_entry(60, 70)]
        assert compute_accuracy_bias(history) is None  # need >= 3

    def test_three_samples_minimum(self):
        # All 50% underestimates
        history = [make_log_entry(60, 90) for _ in range(3)]
        result = compute_accuracy_bias(history)
        assert result is not None

    def test_underestimate_detected(self):
        # Consistently underestimating by 50%: estimated=60, actual=90
        history = [make_log_entry(60, 90) for _ in range(5)]
        result = compute_accuracy_bias(history)
        assert result is not None
        assert result["direction"] == "underestimate"
        assert result["avg_error_pct"] > 0
        assert result["suggested_multiplier"] > 1.0

    def test_overestimate_detected(self):
        # Consistently overestimating: estimated=120, actual=60
        history = [make_log_entry(120, 60) for _ in range(5)]
        result = compute_accuracy_bias(history)
        assert result is not None
        assert result["direction"] == "overestimate"
        assert result["avg_error_pct"] < 0
        assert result["suggested_multiplier"] < 1.0

    def test_small_bias_returns_none(self):
        # Only 10% off → below the 15% significance threshold
        history = [make_log_entry(100, 110) for _ in range(10)]
        result = compute_accuracy_bias(history)
        assert result is None

    def test_skips_entries_without_actuals(self):
        # Mix of entries with and without actuals
        history = [
            make_log_entry(60, None),  # no actual → should be skipped
            make_log_entry(60, None),
            make_log_entry(60, 90),    # only 1 valid sample → < 3, returns None
        ]
        assert compute_accuracy_bias(history) is None

    def test_multiplier_is_clamped(self):
        # 200% underestimate — would give multiplier=3, but should be clamped at 2.5
        history = [make_log_entry(30, 90) for _ in range(5)]
        result = compute_accuracy_bias(history)
        assert result is not None
        assert result["suggested_multiplier"] <= 2.5

    def test_returns_expected_shape(self):
        history = [make_log_entry(60, 96) for _ in range(5)]  # 60% underestimate
        result = compute_accuracy_bias(history)
        assert result is not None
        required_keys = {
            "sample_size", "avg_error_pct", "avg_error_pct_abs",
            "direction", "suggested_multiplier", "example_corrected", "task_type"
        }
        assert required_keys.issubset(result.keys())

    def test_example_corrected_is_15min_multiple(self):
        history = [make_log_entry(60, 96) for _ in range(5)]
        result = compute_accuracy_bias(history)
        assert result is not None
        assert result["example_corrected"] % 15 == 0


# ── _build_prompt ─────────────────────────────────────────────────────────────


class TestBuildPrompt:
    def test_raw_text_appears_in_prompt(self):
        prompt = _build_prompt("review the board deck", None, None, None)
        assert "review the board deck" in prompt

    def test_user_estimate_section_included_when_provided(self):
        prompt = _build_prompt("review the board deck", "2 hours", None, None)
        assert "2 hours" in prompt
        assert "User's Own Estimate" in prompt

    def test_user_estimate_section_absent_when_not_provided(self):
        prompt = _build_prompt("review the board deck", None, None, None)
        assert "User's Own Estimate" not in prompt

    def test_empty_user_estimate_treated_as_none(self):
        prompt = _build_prompt("review the board deck", "   ", None, None)
        assert "User's Own Estimate" not in prompt

    def test_calibration_section_included_when_bias_provided(self):
        bias = {
            "sample_size": 10,
            "avg_error_pct": 40.0,
            "avg_error_pct_abs": 40.0,
            "direction": "underestimate",
            "suggested_multiplier": 1.40,
            "example_corrected": 90,
            "task_type": "work",
        }
        prompt = _build_prompt("write docs", None, bias, None)
        assert "underestimate" in prompt
        assert "40.0%" in prompt

    def test_calibration_section_absent_when_no_bias(self):
        prompt = _build_prompt("write docs", None, None, None)
        assert "Estimation Accuracy" not in prompt

    def test_backlog_section_included_when_provided(self):
        backlog = ["Task Alpha", "Task Beta", "Task Gamma"]
        prompt = _build_prompt("new task", None, None, backlog)
        assert "Task Alpha" in prompt
        assert "Task Beta" in prompt

    def test_backlog_section_absent_when_empty(self):
        prompt = _build_prompt("new task", None, None, [])
        assert "Top Tasks" not in prompt

    def test_today_date_injected(self):
        prompt = _build_prompt("do something by Friday", None, None, None)
        today = date.today().isoformat()
        assert today in prompt

    def test_hours_estimate_included_in_hint(self):
        """User estimate in hours appears in the prompt with the conversion note."""
        prompt = _build_prompt("some task", "1.5 hours", None, None)
        assert "1.5 hours" in prompt
        assert "60" in prompt  # conversion factor mentioned in template


# ── _parse_claude_output ──────────────────────────────────────────────────────


class TestParseClaudeOutput:
    def test_basic_parse(self):
        result = _parse_claude_output(_WORK_SUGGESTION)
        assert result.title == "Review Q2 Board Deck"
        assert result.type == "work"
        assert result.suggested_priority == "top"
        assert result.estimated_duration_minutes == 90
        assert result.confidence == "high"

    def test_deadline_parsed(self):
        result = _parse_claude_output(_PERSONAL_SUGGESTION)
        assert result.optional_deadline_detected == date(2026, 5, 1)

    def test_null_deadline_parsed(self):
        result = _parse_claude_output(_WORK_SUGGESTION)
        assert result.optional_deadline_detected is None

    def test_duration_snapped_to_15_minutes(self):
        data = {**_WORK_SUGGESTION, "estimated_duration_minutes": 73}
        result = _parse_claude_output(data)
        assert result.estimated_duration_minutes % 15 == 0
        assert result.estimated_duration_minutes == 75

    def test_duration_clamped_to_minimum(self):
        data = {**_WORK_SUGGESTION, "estimated_duration_minutes": 5}
        result = _parse_claude_output(data)
        assert result.estimated_duration_minutes == 15

    def test_duration_clamped_to_maximum(self):
        data = {**_WORK_SUGGESTION, "estimated_duration_minutes": 999}
        result = _parse_claude_output(data)
        assert result.estimated_duration_minutes == 480

    def test_title_truncated_if_too_long(self):
        data = {**_WORK_SUGGESTION, "title": "A" * 600}
        result = _parse_claude_output(data)
        assert len(result.title) <= 512

    def test_malformed_deadline_gracefully_handled(self):
        data = {**_WORK_SUGGESTION, "optional_deadline_detected": "next Tuesday"}
        result = _parse_claude_output(data)
        assert result.optional_deadline_detected is None


# ── parse_task_input (integration with mocked Claude) ────────────────────────


class TestParseTaskInput:
    @pytest.mark.asyncio
    async def test_basic_work_task_parsing(self):
        mock_cls, _ = _mock_claude(_WORK_SUGGESTION)
        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            result = await parse_task_input("review the Q2 board deck")

        assert result.ai_available is True
        assert isinstance(result.suggestion, AISuggestion)
        assert result.suggestion.type == "work"
        assert result.suggestion.title == "Review Q2 Board Deck"

    @pytest.mark.asyncio
    async def test_personal_task_with_deadline(self):
        mock_cls, _ = _mock_claude(_PERSONAL_SUGGESTION)
        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            result = await parse_task_input("book summer vacation flights before May")

        assert result.ai_available is True
        assert result.suggestion.type == "personal"
        assert result.suggestion.optional_deadline_detected == date(2026, 5, 1)

    @pytest.mark.asyncio
    async def test_user_estimate_hours_included_in_prompt(self):
        """Verify the prompt passed to Claude includes the user's estimate."""
        mock_cls, mock_client = _mock_claude(_WORK_SUGGESTION)
        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            await parse_task_input("write board deck", user_estimate="2 hours")

        call_args = mock_client.messages.create.call_args
        # The messages list should contain the user estimate in the content
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        if isinstance(messages, list):
            user_content = messages[0]["content"]
        else:
            user_content = str(call_args)
        assert "2 hours" in user_content

    @pytest.mark.asyncio
    async def test_calibration_included_when_bias_detected(self):
        """When history shows consistent underestimation, calibration appears in prompt."""
        history = [make_log_entry(60, 96) for _ in range(5)]  # 60% bias

        mock_cls, mock_client = _mock_claude(_WORK_SUGGESTION)
        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            await parse_task_input("write a proposal", history=history)

        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs.get("messages", [])
        user_content = messages[0]["content"] if messages else ""
        assert "underestimate" in user_content.lower() or "multiplier" in user_content.lower()

    @pytest.mark.asyncio
    async def test_no_calibration_when_insufficient_history(self):
        """Only 2 samples → no calibration section in prompt."""
        history = [make_log_entry(60, 90), make_log_entry(60, 90)]

        mock_cls, mock_client = _mock_claude(_WORK_SUGGESTION)
        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            await parse_task_input("write a proposal", history=history)

        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs.get("messages", [])
        user_content = messages[0]["content"] if messages else ""
        # With insufficient history, calibration section should not appear
        assert "Estimation Accuracy" not in user_content

    @pytest.mark.asyncio
    async def test_backlog_preview_included_in_prompt(self):
        backlog = ["Top priority task", "Second priority task"]
        mock_cls, mock_client = _mock_claude(_WORK_SUGGESTION)
        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            await parse_task_input("new task", backlog_preview=backlog)

        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs.get("messages", [])
        user_content = messages[0]["content"] if messages else ""
        assert "Top priority task" in user_content

    @pytest.mark.asyncio
    async def test_tool_use_is_forced(self):
        """Verify the API call uses forced tool_choice."""
        mock_cls, mock_client = _mock_claude(_WORK_SUGGESTION)
        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            await parse_task_input("something")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs.get("tool_choice") == {
            "type": "tool",
            "name": "submit_task_suggestion",
        }
        assert any(
            t.get("name") == "submit_task_suggestion"
            for t in call_kwargs.get("tools", [])
        )


# ── Graceful degradation ──────────────────────────────────────────────────────


class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_connection_error_returns_fallback(self):
        mock_cls = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock()
        )
        mock_cls.return_value = mock_instance

        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            result = await parse_task_input("some task")

        assert result.ai_available is False
        assert isinstance(result.suggestion, AISuggestion)
        assert result.suggestion.confidence == "low"

    @pytest.mark.asyncio
    async def test_api_status_error_returns_fallback(self):
        mock_cls = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.messages.create.side_effect = anthropic.APIStatusError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body={},
        )
        mock_cls.return_value = mock_instance

        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            result = await parse_task_input("some task")

        assert result.ai_available is False

    @pytest.mark.asyncio
    async def test_timeout_error_returns_fallback(self):
        mock_cls = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.messages.create.side_effect = anthropic.APITimeoutError(
            request=MagicMock()
        )
        mock_cls.return_value = mock_instance

        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            result = await parse_task_input("some task")

        assert result.ai_available is False

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_fallback(self):
        mock_cls = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.messages.create.side_effect = RuntimeError("unexpected")
        mock_cls.return_value = mock_instance

        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            result = await parse_task_input("some task")

        assert result.ai_available is False

    @pytest.mark.asyncio
    async def test_fallback_preserves_raw_text_as_title(self):
        mock_cls = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock()
        )
        mock_cls.return_value = mock_instance

        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            result = await parse_task_input("review the board deck")

        assert "review the board deck" in result.suggestion.title.lower()

    @pytest.mark.asyncio
    async def test_fallback_has_sensible_defaults(self):
        mock_cls = MagicMock()
        mock_instance = AsyncMock()
        mock_instance.messages.create.side_effect = anthropic.APIConnectionError(
            request=MagicMock()
        )
        mock_cls.return_value = mock_instance

        with patch("app.services.ai_service.anthropic.AsyncAnthropic", mock_cls):
            result = await parse_task_input("do something")

        s = result.suggestion
        assert s.type == "work"
        assert s.suggested_priority == "medium"
        assert s.estimated_duration_minutes == 60
        assert s.reasoning != ""
