"""percep_bot_os 入口 — python -m percep_bot_os --config config.yaml"""

from __future__ import annotations

import argparse
import sys

import yaml

from percep_bot_os.framework.manager import ModuleManager


def main() -> int:
    parser = argparse.ArgumentParser(description="percep_bot_os 模块管理系统")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    manager = ModuleManager(config)
    manager.load_modules_from_config()
    return manager.run()


if __name__ == "__main__":
    sys.exit(main())
