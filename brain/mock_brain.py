"""Mock Brain，供 L0-L2 测试使用。"""

from __future__ import annotations

import time

from percep_bot_os.contracts.data_types import BrainDecision, BrainObservation


class MockBrain:
    """模拟大脑，返回预设的 BrainDecision。

    用于测试导航管线，不需要真实的 qwen3-vl 模型。
    """

    def __init__(self, default_intent: str = "navigate") -> None:
        self._default_intent = default_intent
        self._next_intent: str | None = None
        self._next_target_query: str | None = None

    def decide(self, observation: BrainObservation) -> BrainDecision:
        """根据 observation 返回预设决策。"""
        intent = self._next_intent if self._next_intent is not None else self._default_intent
        target_query = self._next_target_query

        self._next_intent = None
        self._next_target_query = None

        return BrainDecision(
            intent=intent,
            target_query=target_query,
            map_goal_id=None,
            mode=intent,
            constraints={},
            requires_confirmation=False,
            confidence=1.0,
            explanation=f"mock decision: {intent}",
            timestamp=observation.timestamp or time.time(),
        )

    def set_response(self, intent: str, target_query: str | None = None) -> None:
        """手动设置下次返回的决策。"""
        self._next_intent = intent
        self._next_target_query = target_query
