"""证据收集器 —— 收集测试证据并生成结构化报告。"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class TestAssertion:
    test_id: str
    description: str
    passed: bool
    actual: str
    expected: str
    details: str = ""


@dataclass
class TestSummary:
    run_id: str
    timestamp: float
    phase: str
    total_tests: int
    passed: int
    failed: int
    duration_seconds: float
    assertions: list[TestAssertion] = field(default_factory=list)


class EvidenceCollector:
    """收集测试证据并生成结构化报告。"""

    def __init__(self, run_id: str, phase: str, output_dir: str = "logs/test_runs") -> None:
        self.run_id = run_id
        self.phase = phase
        self.output_dir = Path(output_dir) / run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assertions: list[TestAssertion] = []
        self.start_time = time.time()
        self.trajectory_data: list[dict] = []
        self.command_data: list[dict] = []

    def add_assertion(
        self,
        test_id: str,
        description: str,
        passed: bool,
        actual: str,
        expected: str,
        details: str = "",
    ) -> None:
        self.assertions.append(
            TestAssertion(
                test_id=test_id,
                description=description,
                passed=passed,
                actual=actual,
                expected=expected,
                details=details,
            )
        )

    def record_trajectory(self, step: int, x: float, y: float, theta: float) -> None:
        self.trajectory_data.append({"step": step, "x": x, "y": y, "theta": theta})

    def record_command(self, step: int, linear_x: float, angular_z: float) -> None:
        self.command_data.append({"step": step, "linear_x": linear_x, "angular_z": angular_z})

    def generate_summary(self) -> TestSummary:
        """生成 TestSummary。"""
        elapsed = time.time() - self.start_time
        passed = sum(1 for a in self.assertions if a.passed)
        failed = sum(1 for a in self.assertions if not a.passed)
        return TestSummary(
            run_id=self.run_id,
            timestamp=self.start_time,
            phase=self.phase,
            total_tests=len(self.assertions),
            passed=passed,
            failed=failed,
            duration_seconds=round(elapsed, 3),
            assertions=list(self.assertions),
        )

    def generate_assertions(self) -> list[dict]:
        """生成 assertions 列表（dict 格式）。"""
        return [asdict(a) for a in self.assertions]

    def save_trajectory_csv(self) -> None:
        """保存 trajectory.csv。"""
        path = self.output_dir / "trajectory.csv"
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["step", "x", "y", "theta"])
            writer.writeheader()
            writer.writerows(self.trajectory_data)

    def save_commands_csv(self) -> None:
        """保存 commands.csv。"""
        path = self.output_dir / "commands.csv"
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["step", "linear_x", "angular_z"])
            writer.writeheader()
            writer.writerows(self.command_data)

    def save_all(self) -> Path:
        """保存所有证据文件到 output_dir，返回目录路径。"""
        summary = self.generate_summary()
        summary_dict = asdict(summary)
        with open(self.output_dir / "summary.json", "w") as f:
            json.dump(summary_dict, f, indent=2, ensure_ascii=False)

        assertions = self.generate_assertions()
        with open(self.output_dir / "assertions.json", "w") as f:
            json.dump(assertions, f, indent=2, ensure_ascii=False)

        if self.trajectory_data:
            self.save_trajectory_csv()

        if self.command_data:
            self.save_commands_csv()

        return self.output_dir
