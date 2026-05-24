from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from playwright.async_api import Page

from .browser_ops import goto_page, safe_click, wait_visible_any
from .config import selector_config
from .correlation import append_alpha_library, extract_structure
from .models import ALPHAS_URL, CorrelationResult, QualityReport, WorkflowConfig
from .paths import FAVORITE_DIR, FAVORITE_LOG_FIELDS, FAVORITE_LOG_FILE, append_csv, now_ts
from .platform_sc import sc_payload_from_metrics


async def add_to_favorites(
    page: Page,
    template_file: str,
    alpha_name: str,
    code: str,
    metrics: dict[str, float],
    quality: QualityReport,
    correlation: CorrelationResult,
    config: WorkflowConfig,
    platform_sc: dict[str, object] | None = None,
) -> str:
    assert correlation.passed, f"自相关红线未通过，禁止收藏：{correlation.reason}"

    favorite_selectors = selector_config(
        config,
        "favorite_button",
        [
            '[title="Add to Favorites"]',
            'button:has-text("Add to Favorites")',
            'button:has-text("Favorite")',
            'button:has-text("收藏")',
            '[aria-label*="favorite" i]',
            '[title*="favorite" i]',
        ],
    )
    try:
        await safe_click(page, favorite_selectors, "Add to Favorites", timeout=12000)
    except Exception:
        logging.info("当前页未找到收藏按钮，尝试进入 Alphas 页面定位")
        await goto_page(page, f"{ALPHAS_URL}/unsubmitted")
        await wait_visible_any(page, ["body"], timeout=15000)
        await safe_click(page, favorite_selectors, "Add to Favorites", timeout=15000)

    await confirm_favorite_dialog(page)
    screenshot = str(FAVORITE_DIR / f"{alpha_name}_{now_ts()}_favorite.png")
    await page.screenshot(path=screenshot, full_page=True)
    sc_payload = sc_payload_from_metrics(metrics if isinstance(metrics, dict) else {}, platform_sc)
    platform_sc_json = json.dumps(platform_sc, ensure_ascii=False, default=str) if isinstance(platform_sc, dict) else ""

    append_csv(
        FAVORITE_LOG_FILE,
        FAVORITE_LOG_FIELDS,
        {
            "time": datetime.now().isoformat(timespec="seconds"),
            "template_file": template_file,
            "alpha_name": alpha_name,
            "code": code,
            "metrics_json": json.dumps(metrics, ensure_ascii=False),
            "quality_json": json.dumps(quality.to_dict(), ensure_ascii=False),
            "screenshot": screenshot,
            "platform_sc_status": sc_payload.get("platform_sc_status", ""),
            "platform_sc_max": sc_payload.get("platform_sc_max", ""),
            "platform_sc_min": sc_payload.get("platform_sc_min", ""),
            "platform_sc_abs_max": sc_payload.get("platform_sc_abs_max", ""),
            "platform_sc_json": platform_sc_json,
        },
    )
    append_alpha_library(
        alpha_name,
        code,
        extract_structure(code),
        metrics,
        enable_v2_engine=config.enable_v2_engine,
        enable_behavior_sc_pipeline=config.enable_v2_engine
        and config.enable_behavior_sc_pipeline
        and config.v2_rollout_phase >= 2,
        platform_sc=platform_sc,
    )
    return screenshot


async def confirm_favorite_dialog(page: Page) -> None:
    selectors = [
        'button:has-text("Add Alpha to List")',
        'button:has-text("Add Alpha and View List")',
        'button:has-text("Add")',
        'button:has-text("OK")',
        'button:has-text("确认")',
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if not await locator.is_visible(timeout=1200):
                continue
            text = await locator.inner_text(timeout=1000)
            if re.search(r"\bSubmit\b|提交", text, re.I):
                raise RuntimeError("禁止点击 Submit/提交")
            await locator.click(force=True)
            return
        except Exception:
            continue
