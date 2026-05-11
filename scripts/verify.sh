#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== verify.sh @ $REPO_ROOT ==="

echo ">>> [1/4] 依赖安装"
pip install -e ".[dev]" -q

echo ">>> [2/4] lint (ruff)"
ruff check .

echo ">>> [3/4] 类型检查 (mypy, 非阻塞)"
mypy --ignore-missing-imports navigation_core/ || true

echo ">>> [4/4] 测试 (pytest)"
pytest tests/ -q --maxfail=10

echo "================================================================"
echo " verify.sh: ALL OK"
echo "================================================================"
