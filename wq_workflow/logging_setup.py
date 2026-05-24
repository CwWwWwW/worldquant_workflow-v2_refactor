from __future__ import annotations

import logging
import sys

from .paths import WORKFLOW_LOG_FILE


DISCLAIMER = """
合规免责声明：
本脚本仅用于已获授权的研究和个人工作流辅助。请遵守 WorldQuant Brain 平台规则、账号安全规则和当地法律法规。
脚本不会执行任何 Submit/提交 操作；只在平台质量要求通过且本地自相关红线通过后 Add to Favorites。
账号、密码和 API Key 必须来自环境变量或本地配置文件，禁止写入代码。
""".strip()


def setup_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(WORKFLOW_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

