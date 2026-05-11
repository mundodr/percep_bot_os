"""Brain fallback 策略，用于错误/超时/低置信度时的安全决策。"""

from __future__ import annotations

import time

from percep_bot_os.contracts.data_types import BrainDecision


def _make_fallback(reason: str) -> BrainDecision:
    return BrainDecision(
        intent="pause",
        target_query=None,
        map_goal_id=None,
        mode="pause",
        constraints={},
        requires_confirmation=False,
        confidence=0.0,
        explanation=f"fallback: {reason}",
        timestamp=time.time(),
    )


FALLBACK_DECISIONS: dict[str, BrainDecision] = {
    "error": _make_fallback("error"),
    "timeout": _make_fallback("timeout"),
    "low_confidence": _make_fallback("low_confidence"),
}


def get_fallback(reason: str) -> BrainDecision:
    """根据原因获取 fallback 决策。若原因未知，返回通用 pause。"""
    if reason in FALLBACK_DECISIONS:
        return FALLBACK_DECISIONS[reason]
    return _make_fallback(reason)
