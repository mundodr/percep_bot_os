"""BrainDecision 校验器和安全解析工具。"""

from __future__ import annotations

import time

from percep_bot_os.contracts.data_types import BrainDecision

BRAIN_INTENT_WHITELIST: frozenset[str] = frozenset(
    {
        "navigate",
        "explore",
        "semantic_search",
        "inspect",
        "return_home",
        "pause",
        "stop",
        "ask_user",
    }
)

VELOCITY_FIELD_BLACKLIST: frozenset[str] = frozenset(
    {
        "linear_x",
        "angular_z",
        "linear_y",
        "angular_x",
        "angular_y",
        "velocity",
        "speed",
    }
)


class BrainDecisionValidator:
    """校验 BrainDecision 是否合规。"""

    def validate(self, decision: BrainDecision) -> tuple[bool, list[str]]:
        """返回 (是否有效, 错误列表)。

        检查项:
        - intent 在白名单内
        - confidence 在 [0, 1]
        - 不包含速度字段
        - timestamp > 0
        - mode 非空
        """
        errors: list[str] = []

        if decision.intent not in BRAIN_INTENT_WHITELIST:
            errors.append(
                f"intent '{decision.intent}' 不在白名单 {sorted(BRAIN_INTENT_WHITELIST)} 内"
            )

        if not (0.0 <= decision.confidence <= 1.0):
            errors.append(f"confidence {decision.confidence} 超出 [0, 1] 范围")

        for field_name in VELOCITY_FIELD_BLACKLIST:
            if hasattr(decision, field_name):
                errors.append(f"BrainDecision 不允许包含速度字段 '{field_name}'")
            if field_name in decision.constraints:
                errors.append(f"constraints 中不允许包含速度字段 '{field_name}'")

        if decision.timestamp <= 0:
            errors.append(f"timestamp {decision.timestamp} 必须 > 0")

        if not decision.mode:
            errors.append("mode 不能为空")

        return (len(errors) == 0, errors)

    def safe_parse(self, raw: dict, fallback_intent: str = "pause") -> BrainDecision:
        """从 dict 安全解析，失败时返回 fallback decision。"""
        try:
            decision = BrainDecision(
                intent=raw.get("intent", fallback_intent),
                target_query=raw.get("target_query"),
                map_goal_id=raw.get("map_goal_id"),
                mode=raw.get("mode", fallback_intent),
                constraints=raw.get("constraints", {}),
                requires_confirmation=raw.get("requires_confirmation", False),
                confidence=float(raw.get("confidence", 0.0)),
                explanation=raw.get("explanation", ""),
                timestamp=float(raw.get("timestamp", time.time())),
            )
            ok, _ = self.validate(decision)
            if ok:
                return decision
        except (TypeError, ValueError, KeyError):
            pass

        return BrainDecision(
            intent=fallback_intent,
            target_query=None,
            map_goal_id=None,
            mode=fallback_intent,
            constraints={},
            requires_confirmation=False,
            confidence=0.0,
            explanation="safe_parse fallback",
            timestamp=time.time(),
        )
