"""BrainDecision 校验器、MockBrain、Fallback 测试。"""

from __future__ import annotations

from brain.brain_decision_schema import BrainDecisionValidator
from brain.fallback import get_fallback
from brain.mock_brain import MockBrain
from percep_bot_os.contracts.data_types import BrainDecision, BrainObservation


def _make_observation(ts: float = 1.0) -> BrainObservation:
    return BrainObservation(
        timestamp=ts,
        user_command="test",
        image_ref=None,
        map_summary={},
        semantic_summary={},
        navigation_state={},
        exploration_state={},
        safety_state={},
    )


# ── BrainDecisionValidator ───────────────────────────────────────────


def test_valid_decision_passes() -> None:
    d = BrainDecision(
        intent="navigate",
        target_query="kitchen",
        map_goal_id=None,
        mode="navigate",
        constraints={},
        requires_confirmation=False,
        confidence=0.8,
        explanation="go to kitchen",
        timestamp=1.0,
    )
    ok, errors = BrainDecisionValidator().validate(d)
    assert ok is True
    assert errors == []


def test_invalid_intent_fails() -> None:
    d = BrainDecision(
        intent="fly_away",
        target_query=None,
        map_goal_id=None,
        mode="navigate",
        constraints={},
        requires_confirmation=False,
        confidence=0.5,
        explanation="",
        timestamp=1.0,
    )
    ok, errors = BrainDecisionValidator().validate(d)
    assert ok is False
    assert any("fly_away" in e for e in errors)


def test_invalid_confidence_fails() -> None:
    d = BrainDecision(
        intent="pause",
        target_query=None,
        map_goal_id=None,
        mode="pause",
        constraints={},
        requires_confirmation=False,
        confidence=1.5,
        explanation="",
        timestamp=1.0,
    )
    ok, errors = BrainDecisionValidator().validate(d)
    assert ok is False
    assert any("confidence" in e for e in errors)


# ── safe_parse ───────────────────────────────────────────────────────


def test_safe_parse_valid() -> None:
    raw = {
        "intent": "explore",
        "target_query": None,
        "map_goal_id": None,
        "mode": "explore",
        "constraints": {},
        "requires_confirmation": False,
        "confidence": 0.9,
        "explanation": "explore area",
        "timestamp": 2.0,
    }
    result = BrainDecisionValidator().safe_parse(raw)
    assert result.intent == "explore"
    assert result.confidence == 0.9


def test_safe_parse_invalid() -> None:
    raw = {"intent": "fly_away", "confidence": -999}
    result = BrainDecisionValidator().safe_parse(raw)
    assert result.intent == "pause"
    assert result.confidence == 0.0


# ── MockBrain ────────────────────────────────────────────────────────


def test_mock_brain_default() -> None:
    brain = MockBrain()
    obs = _make_observation()
    decision = brain.decide(obs)
    assert decision.intent == "navigate"
    assert decision.confidence == 1.0


def test_mock_brain_custom() -> None:
    brain = MockBrain()
    brain.set_response("semantic_search", target_query="red chair")
    obs = _make_observation()
    decision = brain.decide(obs)
    assert decision.intent == "semantic_search"
    assert decision.target_query == "red chair"

    second = brain.decide(obs)
    assert second.intent == "navigate"
    assert second.target_query is None


# ── Fallback ─────────────────────────────────────────────────────────


def test_fallback_error() -> None:
    fb = get_fallback("error")
    assert fb.intent == "pause"
    assert fb.confidence == 0.0


def test_fallback_timeout() -> None:
    fb = get_fallback("timeout")
    assert fb.intent == "pause"
    assert fb.confidence == 0.0
