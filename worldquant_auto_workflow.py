#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""WorldQuant + DeepSeek 自动迭代工作流入口。

流程：
1. 接收用户给予的文本模板。
2. DeepSeek 筛选、分割并保存模板。
3. 逐个模板由 DeepSeek 优化成可用 Alpha。
4. 登录 WorldQuant，真实回测，等待平台完成。
5. 平台错误或质量未达标时，将错误/IS Summary/IS Testing Status 交回 DeepSeek 修复。
6. 平台质量通过且本地自相关红线通过后，Add to Favorites。

绝不执行 Submit/提交。
"""

from __future__ import annotations

from wq_workflow.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
