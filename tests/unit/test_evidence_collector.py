"""证据收集器单元测试。"""

from __future__ import annotations

import json

from tests.test_runner.evidence_collector import EvidenceCollector


def test_collector_creation(tmp_path):
    """创建不报错。"""
    collector = EvidenceCollector(
        run_id="test-001", phase="unit", output_dir=str(tmp_path)
    )
    assert collector.run_id == "test-001"
    assert collector.phase == "unit"
    assert (tmp_path / "test-001").is_dir()


def test_add_assertion(tmp_path):
    """添加断言记录。"""
    collector = EvidenceCollector(
        run_id="test-002", phase="unit", output_dir=str(tmp_path)
    )
    collector.add_assertion(
        test_id="T-1",
        description="测试断言",
        passed=True,
        actual="1.0",
        expected="1.0",
        details="无",
    )
    assert len(collector.assertions) == 1
    assert collector.assertions[0].test_id == "T-1"
    assert collector.assertions[0].passed is True


def test_generate_summary(tmp_path):
    """生成摘要正确。"""
    collector = EvidenceCollector(
        run_id="test-003", phase="unit", output_dir=str(tmp_path)
    )
    collector.add_assertion("T-1", "通过", True, "ok", "ok")
    collector.add_assertion("T-2", "失败", False, "bad", "good")
    collector.add_assertion("T-3", "通过", True, "ok", "ok")

    summary = collector.generate_summary()
    assert summary.run_id == "test-003"
    assert summary.phase == "unit"
    assert summary.total_tests == 3
    assert summary.passed == 2
    assert summary.failed == 1
    assert summary.duration_seconds >= 0
    assert len(summary.assertions) == 3


def test_save_all(tmp_path):
    """保存文件到磁盘。"""
    collector = EvidenceCollector(
        run_id="test-004", phase="unit", output_dir=str(tmp_path)
    )
    collector.add_assertion("T-1", "ok", True, "1", "1")
    collector.record_trajectory(0, 1.0, 2.0, 0.5)
    collector.record_command(0, 0.3, 0.1)

    out = collector.save_all()
    assert (out / "summary.json").exists()
    assert (out / "assertions.json").exists()
    assert (out / "trajectory.csv").exists()
    assert (out / "commands.csv").exists()

    with open(out / "summary.json") as f:
        summary = json.load(f)
    assert summary["run_id"] == "test-004"
    assert summary["passed"] == 1

    with open(out / "assertions.json") as f:
        assertions = json.load(f)
    assert len(assertions) == 1
    assert assertions[0]["test_id"] == "T-1"


def test_trajectory_csv(tmp_path):
    """轨迹 CSV 格式正确。"""
    collector = EvidenceCollector(
        run_id="test-005", phase="unit", output_dir=str(tmp_path)
    )
    collector.record_trajectory(0, 1.0, 2.0, 0.0)
    collector.record_trajectory(1, 1.1, 2.0, 0.1)
    collector.record_trajectory(2, 1.2, 2.1, 0.2)
    collector.save_trajectory_csv()

    csv_path = tmp_path / "test-005" / "trajectory.csv"
    assert csv_path.exists()

    lines = csv_path.read_text().strip().split("\n")
    assert lines[0] == "step,x,y,theta"
    assert len(lines) == 4  # header + 3 data rows
    row1 = lines[1].split(",")
    assert row1[0] == "0"
    assert float(row1[1]) == 1.0
