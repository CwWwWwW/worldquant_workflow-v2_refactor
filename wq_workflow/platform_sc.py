from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import Locator, Page

from .paths import RUNTIME_DIR
from .safe_io import atomic_write_json


LIVE_SC_PREFIX = "[LivePlatformSC]"
DEBUG_DIR = RUNTIME_DIR / "debug"
ABSOLUTE_CORRELATION_XPATH = (
    "/html/body/div[5]/div/div[3]/section/div/div[1]/div[2]/div/div[1]/div[2]/div/div[5]/div[2]/div/div[1]/div[4]/div[2]"
)
CORRELATION_SELECTORS = [
    ".correlation__content-status-time-refresh",
    "[class*='correlation__content' i]",
    "[class*='correlation' i]",
]
TEXT_NEARBY_LABELS = ["Self-correlation", "Self correlation", "Correlation"]
PLATFORM_SC_METRIC_KEYS = [
    "platform_sc_status",
    "platform_sc_max",
    "platform_sc_min",
    "platform_sc_abs_max",
    "real_self_corr",
    "sc_source",
    "correlation_quality",
    "submission_quality",
]


def _log(message: str, *args: Any) -> None:
    logging.info("%s " + message, LIVE_SC_PREFIX, *args)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def text_hash(text: str) -> str:
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()[:12]


def text_preview(text: str, limit: int = 160) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    return compact[:limit]


async def ensure_show_test_period_expanded(page: Page, retries: int = 1) -> dict[str, Any]:
    """Expand Show test period safely, reusing the existing result-page helper."""
    try:
        from .simulate import detect_and_click_show_test_period, show_test_period_revealed_on_page
    except Exception as exc:
        _log("show_test_period expanded=false method=import_error error=%s", exc)
        return {"expanded": False, "method": "import_error", "error": str(exc)}

    try:
        if await show_test_period_revealed_on_page(page):
            _log("show_test_period expanded=true method=already_expanded")
            return {"expanded": True, "method": "already_expanded"}
    except Exception:
        logging.debug("Show test period revealed check failed", exc_info=True)

    attempts = max(1, int(retries) + 1)
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            clicked = await detect_and_click_show_test_period(page)
            await page.wait_for_timeout(800)
            expanded = bool(clicked)
            try:
                expanded = expanded or bool(await show_test_period_revealed_on_page(page))
            except Exception:
                pass
            if expanded:
                method = "button_text" if clicked else "post_click_detected"
                _log("show_test_period expanded=true method=%s", method)
                return {"expanded": True, "method": method, "attempt": attempt}
        except Exception as exc:
            last_error = str(exc)
            logging.debug("Show test period click attempt failed", exc_info=True)
        if attempt < attempts:
            await page.wait_for_timeout(800)

    _log("show_test_period expanded=false method=button_text error=%s", last_error)
    return {"expanded": False, "method": "button_text", "error": last_error}


async def locate_correlation_panel(page: Page) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    marker = f"wq-platform-sc-{uuid.uuid4().hex}"

    for selector in CORRELATION_SELECTORS:
        found = await _mark_panel_from_css(page, selector, marker)
        attempts.append({"selector": selector, "found": bool(found)})
        if found:
            _log("correlation_panel_found=true selector=%s", selector)
            return {
                "found": True,
                "selector": selector,
                "locator": page.locator(f'[data-wq-platform-sc-panel="{marker}"]').first,
                "attempts": attempts,
            }

    for label in TEXT_NEARBY_LABELS:
        found = await _mark_panel_from_text(page, label, marker)
        selector = f"text_nearby:{label}"
        attempts.append({"selector": selector, "found": bool(found)})
        if found:
            _log("correlation_panel_found=true selector=%s", selector)
            return {
                "found": True,
                "selector": selector,
                "locator": page.locator(f'[data-wq-platform-sc-panel="{marker}"]').first,
                "attempts": attempts,
            }

    found = await _mark_panel_from_xpath(page, ABSOLUTE_CORRELATION_XPATH, marker)
    attempts.append({"selector": "xpath_absolute_fallback", "found": bool(found)})
    if found:
        _log("correlation_panel_found=true selector=xpath_absolute_fallback")
        return {
            "found": True,
            "selector": "xpath_absolute_fallback",
            "locator": page.locator(f'[data-wq-platform-sc-panel="{marker}"]').first,
            "attempts": attempts,
        }

    _log("correlation_panel_found=false selector=none")
    return {"found": False, "selector": "", "locator": None, "attempts": attempts}


async def _mark_panel_from_css(page: Page, selector: str, marker: str) -> bool:
    try:
        return bool(
            await page.evaluate(
                """({selector, marker}) => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const attrs = el => [
                        el.tagName,
                        el.id || '',
                        String(el.className || ''),
                        el.getAttribute('role') || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('data-testid') || ''
                    ].join(' ');
                    const promote = el => {
                        const status = el.closest('.correlation__content-status');
                        if (status && visible(status)) return status;
                        const box = el.closest('#alphas-correlation,.correlation__content,[class*="correlation__content" i]');
                        if (box && visible(box)) return box;
                        let best = el;
                        for (let node = el, depth = 0; node && depth < 5; node = node.parentElement, depth += 1) {
                            if (node === document.body || node === document.documentElement) break;
                            const text = normalize(node.innerText || node.textContent || '');
                            const meta = attrs(node);
                            if (/correlation|self[- ]?correlation/i.test(text + ' ' + meta) && text.length <= 1200) {
                                best = node;
                            }
                        }
                        return best;
                    };
                    let nodes = [];
                    try {
                        nodes = Array.from(document.querySelectorAll(selector)).slice(0, 80);
                    } catch (_) {
                        return false;
                    }
                    for (const el of nodes) {
                        if (!visible(el)) continue;
                        const panel = promote(el);
                        if (!visible(panel)) continue;
                        panel.setAttribute('data-wq-platform-sc-panel', marker);
                        return true;
                    }
                    return false;
                }""",
                {"selector": selector, "marker": marker},
            )
        )
    except Exception:
        return False


async def _mark_panel_from_text(page: Page, label: str, marker: str) -> bool:
    try:
        return bool(
            await page.evaluate(
                """({label, marker}) => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const labelRe = /self/i.test(label) ? /self[-\\s]?correlation/i : /correlation/i;
                    const score = node => {
                        const text = normalize(node.innerText || node.textContent || '');
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        let value = 0;
                        if (/self[- ]?correlation/i.test(text)) value += 8;
                        if (/correlation/i.test(text + ' ' + attrs)) value += 4;
                        if (/max|min|abs/i.test(text)) value += 2;
                        if (text.length > 0 && text.length <= 4500) value += 1;
                        return value;
                    };
                    let best = null;
                    let bestScore = -1;
                    for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 9000)) {
                        if (!visible(el)) continue;
                        const text = normalize(el.innerText || el.textContent || '');
                        if (!labelRe.test(text)) continue;
                        let panel = el;
                        for (let node = el, depth = 0; node && depth < 7; node = node.parentElement, depth += 1) {
                            if (node === document.body || node === document.documentElement) break;
                            const nodeText = normalize(node.innerText || node.textContent || '');
                            if (!nodeText || nodeText.length > 4500) continue;
                            const nodeScore = score(node);
                            if (nodeScore >= bestScore) {
                                panel = node;
                                best = node;
                                bestScore = nodeScore;
                            }
                        }
                        if (!best) {
                            best = panel;
                            bestScore = score(panel);
                        }
                    }
                    if (!best || !visible(best)) return false;
                    best.setAttribute('data-wq-platform-sc-panel', marker);
                    return true;
                }""",
                {"label": label, "marker": marker},
            )
        )
    except Exception:
        return False


async def _mark_panel_from_xpath(page: Page, xpath: str, marker: str) -> bool:
    try:
        return bool(
            await page.evaluate(
                """({xpath, marker}) => {
                    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    const el = result.singleNodeValue;
                    if (!el || !el.setAttribute) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    if (style.display === 'none' || style.visibility === 'hidden' || rect.width <= 0 || rect.height <= 0) return false;
                    el.setAttribute('data-wq-platform-sc-panel', marker);
                    return true;
                }""",
                {"xpath": xpath, "marker": marker},
            )
        )
    except Exception:
        return False


async def wait_and_extract_platform_sc(
    page: Page,
    timeout_seconds: int = 90,
    artifact_prefix: str = "platform_sc",
) -> dict[str, Any]:
    started = time.time()
    show_result = await ensure_show_test_period_expanded(page, retries=1)
    panel_info = await locate_correlation_panel(page)
    selector = str(panel_info.get("selector") or "")
    panel = panel_info.get("locator")
    attempts = panel_info.get("attempts") if isinstance(panel_info.get("attempts"), list) else []

    if not panel_info.get("found") or panel is None:
        elapsed = int(time.time() - started)
        result = {
            "status": "missing",
            "selector": selector,
            "max": None,
            "min": None,
            "abs_max": None,
            "elapsed_seconds": elapsed,
            "raw_text_preview": "",
            "raw_text_hash": "",
            "show_test_period": show_result,
            "selector_attempts": attempts,
        }
        result = await save_platform_sc_artifacts(page, None, result, artifact_prefix=artifact_prefix)
        return result

    refresh_result = await click_platform_sc_refresh(page)
    deadline = started + max(1, int(timeout_seconds))
    consecutive_complete = 0
    last_result: dict[str, Any] = {}
    last_text = ""

    while time.time() < deadline:
        elapsed = int(time.time() - started)
        text = await _safe_panel_text(panel)
        last_text = text
        parsed = parse_platform_sc_text(text)
        status = classify_platform_sc_text(text, parsed)
        raw_hash = text_hash(text)
        preview = text_preview(text)
        last_result = {
            "status": status,
            "selector": selector,
            "max": parsed.get("max"),
            "min": parsed.get("min"),
            "abs_max": parsed.get("abs_max"),
            "elapsed_seconds": elapsed,
            "raw_text_preview": preview,
            "raw_text_hash": raw_hash,
            "show_test_period": show_result,
            "sc_refresh": refresh_result,
            "selector_attempts": attempts,
        }

        if status == "complete":
            consecutive_complete += 1
            if consecutive_complete >= 2:
                _log(
                    "complete max=%s min=%s abs_max=%s elapsed=%ss",
                    last_result.get("max"),
                    last_result.get("min"),
                    last_result.get("abs_max"),
                    elapsed,
                )
                return await save_platform_sc_artifacts(page, panel, last_result, artifact_prefix=artifact_prefix)
            _log(
                'waiting elapsed=%ss status=complete_candidate text_hash=%s text_preview="%s"',
                elapsed,
                raw_hash,
                preview,
            )
        else:
            consecutive_complete = 0
            _log(
                'waiting elapsed=%ss status=%s text_hash=%s text_preview="%s"',
                elapsed,
                status,
                raw_hash,
                preview,
            )

        await asyncio.sleep(2)

    elapsed = int(time.time() - started)
    if not last_result:
        last_result = {
            "selector": selector,
            "max": None,
            "min": None,
            "abs_max": None,
            "raw_text_preview": text_preview(last_text),
            "raw_text_hash": text_hash(last_text),
            "show_test_period": show_result,
            "sc_refresh": refresh_result,
            "selector_attempts": attempts,
        }
    last_result["status"] = "timeout"
    last_result["elapsed_seconds"] = elapsed
    last_result = await save_platform_sc_artifacts(page, panel, last_result, artifact_prefix=artifact_prefix, timeout=True)
    _log("timeout elapsed=%ss artifacts=%s", elapsed, json.dumps(last_result.get("artifacts", {}), ensure_ascii=False))
    return last_result


async def click_platform_sc_refresh(page: Page) -> dict[str, Any]:
    """Click the real self-correlation refresh/check trigger inside the correlation panel once."""
    selector = "#alphas-correlation .correlation__content-status-time-refresh"
    try:
        info = await page.evaluate(
            """selector => {
                const el = document.querySelector(selector) || document.querySelector('.correlation__content-status-time-refresh');
                if (!el) return {clicked: false, selector, reason: 'missing'};
                const visible = node => {
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                if (!visible(el)) return {clicked: false, selector, reason: 'not_visible'};
                el.scrollIntoView({block: 'center', inline: 'center'});
                const rect = el.getBoundingClientRect();
                window.__wq_platform_sc_refresh_box = {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                return {
                    clicked: false,
                    selector,
                    reason: 'ready_for_mouse_click',
                    box: window.__wq_platform_sc_refresh_box,
                    cursor: window.getComputedStyle(el).cursor || ''
                };
            }""",
            selector,
        )
        if not isinstance(info, dict) or not info.get("box"):
            _log("sc_refresh_clicked=false selector=%s reason=%s", selector, (info or {}).get("reason", "unknown") if isinstance(info, dict) else "unknown")
            return info if isinstance(info, dict) else {"clicked": False, "selector": selector, "reason": "unknown"}
        box = info.get("box") if isinstance(info.get("box"), dict) else {}
        x = float(box.get("x") or 0) + float(box.get("w") or 0) / 2.0
        y = float(box.get("y") or 0) + float(box.get("h") or 0) / 2.0
        await page.mouse.click(x, y)
        await page.wait_for_timeout(1000)
        result = {"clicked": True, "selector": selector, "method": "mouse_center", "cursor": info.get("cursor", "")}
        _log("sc_refresh_clicked=true selector=%s method=mouse_center", selector)
        return result
    except Exception as exc:
        _log("sc_refresh_clicked=false selector=%s reason=%s", selector, exc)
        return {"clicked": False, "selector": selector, "reason": str(exc)}


async def _safe_panel_text(panel: Locator) -> str:
    try:
        return await panel.inner_text(timeout=3000)
    except Exception:
        try:
            return await panel.text_content(timeout=3000) or ""
        except Exception:
            return ""


async def _safe_panel_html(panel: Locator | None) -> str:
    if panel is None:
        return ""
    try:
        return await panel.evaluate("el => el.outerHTML")
    except Exception:
        return ""


def classify_platform_sc_text(text: str, parsed: dict[str, Any] | None = None) -> str:
    parsed = parsed or parse_platform_sc_text(text)
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return "unknown"
    has_values = parsed.get("max") is not None or parsed.get("min") is not None or parsed.get("abs_max") is not None
    pending = bool(re.search(r"\b(pending|loading|checking|calculating|running|queued|in progress|waiting)\b", compact, re.I))
    refresh_only = bool(re.search(r"\brefresh(?:ing)?\b", compact, re.I))
    if has_values and not pending:
        return "complete"
    if pending or refresh_only:
        return "pending"
    return "unknown"


def parse_platform_sc_text(text: str) -> dict[str, float | None]:
    compact = re.sub(r"\s+", " ", text or "").strip()
    result: dict[str, float | None] = {"max": None, "min": None, "abs_max": None}
    if not compact:
        return result

    label_patterns = [
        ("abs_max", r"\b(?:abs(?:olute)?[\s_-]*max(?:imum)?|abs[\s_-]*corr(?:elation)?)\b\s*[:=]?\s*(-?\d+(?:\.\d+)?%?)"),
        ("max", r"\b(?:max(?:imum)?|highest)\b\s*[:=]?\s*(-?\d+(?:\.\d+)?%?)"),
        ("min", r"\b(?:min(?:imum)?|lowest)\b\s*[:=]?\s*(-?\d+(?:\.\d+)?%?)"),
    ]
    for key, pattern in label_patterns:
        match = re.search(pattern, compact, re.I)
        if match:
            result[key] = _parse_number(match.group(1))

    values: list[float] = []
    if "correlation" in compact.lower() and all(result[key] is None for key in ("max", "min", "abs_max")):
        for raw in re.findall(r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?%?", compact):
            value = _parse_number(raw)
            if value is None:
                continue
            if abs(value) <= 1.000001:
                values.append(value)
        if values:
            result["max"] = max(values)
            result["min"] = min(values)
            result["abs_max"] = max(abs(value) for value in values)

    if result["abs_max"] is None:
        candidates = [value for value in (result["max"], result["min"]) if value is not None]
        if candidates:
            result["abs_max"] = max(abs(value) for value in candidates)
    if result["max"] is None and result["abs_max"] is not None:
        result["max"] = result["abs_max"]
    if result["min"] is None and result["max"] is not None:
        result["min"] = result["max"]
    return result


def platform_sc_abs_value(platform_sc: dict[str, Any] | None) -> float | None:
    if not isinstance(platform_sc, dict):
        return None
    values: list[float] = []
    for key in ("abs_max", "max", "min"):
        value = _coerce_sc_float(platform_sc.get(key))
        if value is not None:
            values.append(abs(value))
    return max(values) if values else None


def is_platform_sc_too_high(platform_sc: dict[str, Any] | None, threshold: float = 0.7) -> bool:
    if not isinstance(platform_sc, dict) or platform_sc.get("status") != "complete":
        return False
    value = platform_sc_abs_value(platform_sc)
    return bool(value is not None and value > float(threshold))


def apply_platform_sc_to_metrics(metrics: dict[str, Any] | None, platform_sc: dict[str, Any] | None) -> dict[str, Any]:
    enriched: dict[str, Any] = dict(metrics or {})
    platform_sc = platform_sc if isinstance(platform_sc, dict) else {"status": "unknown"}
    status = str(platform_sc.get("status") or "unknown")
    enriched["platform_sc_status"] = status
    if status == "complete":
        max_value = _coerce_sc_float(platform_sc.get("max"))
        min_value = _coerce_sc_float(platform_sc.get("min"))
        abs_value = platform_sc_abs_value(platform_sc)
        if max_value is not None:
            enriched["platform_sc_max"] = max_value
        if min_value is not None:
            enriched["platform_sc_min"] = min_value
        if abs_value is not None:
            enriched["platform_sc_abs_max"] = abs_value
            enriched["real_self_corr"] = abs_value
            enriched["sc_source"] = "platform"
    else:
        if "estimated_self_corr" in enriched and enriched.get("estimated_self_corr") not in (None, ""):
            enriched.setdefault("sc_source", "local_proxy")
        else:
            enriched.setdefault("sc_source", "none")
    return apply_correlation_quality(enriched)


def apply_correlation_quality(metrics: dict[str, Any] | None) -> dict[str, Any]:
    enriched: dict[str, Any] = dict(metrics or {})
    real = _first_float(enriched, ["real_self_corr", "platform_sc_abs_max"])
    if real is not None:
        if real >= 0.90:
            enriched["correlation_quality"] = "severe"
            enriched["submission_quality"] = "blocked_by_sc"
        elif real >= 0.85:
            enriched["correlation_quality"] = "high_risk"
            enriched["submission_quality"] = "bad_sc"
        elif real > 0.70:
            enriched["correlation_quality"] = "medium_risk"
            enriched["submission_quality"] = "weak_sc"
        else:
            enriched["correlation_quality"] = "acceptable"
            enriched["submission_quality"] = "candidate"
        enriched.setdefault("sc_source", "platform")
        return enriched

    estimated = _first_float(
        enriched,
        ["estimated_self_corr", "structure_similarity", "semantic_similarity", "char_similarity"],
    )
    if estimated is not None:
        if estimated >= 0.90:
            enriched["correlation_quality"] = "local_high_risk"
            enriched["submission_quality"] = "local_proxy_risk"
        elif estimated >= 0.75:
            enriched["correlation_quality"] = "local_medium_risk"
            enriched["submission_quality"] = "candidate_with_proxy_warning"
        else:
            enriched["correlation_quality"] = "acceptable"
            enriched["submission_quality"] = "candidate"
        enriched.setdefault("sc_source", "local_proxy")
        return enriched

    enriched.setdefault("correlation_quality", "unknown")
    enriched.setdefault("submission_quality", "candidate")
    enriched.setdefault("sc_source", "none")
    return enriched


def sc_payload_from_metrics(metrics: dict[str, Any] | None, platform_sc: dict[str, Any] | None = None) -> dict[str, Any]:
    metrics = metrics if isinstance(metrics, dict) else {}
    payload = {key: metrics.get(key) for key in PLATFORM_SC_METRIC_KEYS if key in metrics}
    if isinstance(platform_sc, dict) and platform_sc:
        payload["platform_sc"] = platform_sc
    return payload


def sc_reward_multiplier(metrics: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    metrics = metrics if isinstance(metrics, dict) else {}
    real = _first_float(metrics, ["real_self_corr", "platform_sc_abs_max"])
    if real is not None:
        if real >= 0.90:
            return 0.15, {"sc_penalty": "severe_sc_penalty", "real_self_corr": real}
        if real >= 0.85:
            return 0.35, {"sc_penalty": "high_sc_penalty", "real_self_corr": real}
        if real > 0.70:
            return 0.70, {"sc_penalty": "medium_sc_penalty", "real_self_corr": real}
        return 1.0, {"sc_penalty": "", "real_self_corr": real}
    estimated = _coerce_sc_float(metrics.get("estimated_self_corr"))
    if estimated is not None and estimated >= 0.75:
        return 0.85, {"sc_penalty": "local_proxy_sc_penalty", "estimated_self_corr": estimated}
    return 1.0, {}


def strong_feedback_allowed(metrics: dict[str, Any] | None) -> bool:
    real = _first_float(metrics if isinstance(metrics, dict) else {}, ["real_self_corr", "platform_sc_abs_max"])
    return not (real is not None and real >= 0.85)


def _parse_number(raw: str) -> float | None:
    try:
        text = str(raw).strip()
        is_percent = text.endswith("%")
        value = float(text.rstrip("%"))
        if is_percent:
            value = value / 100.0
        if abs(value) > 1.000001:
            return None
        return round(value, 6)
    except (TypeError, ValueError):
        return None


def _coerce_sc_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if abs(number) > 1.000001:
        return None
    return round(number, 6)


def _first_float(metrics: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _coerce_sc_float(metrics.get(key))
        if value is not None:
            return abs(value)
    return None


async def save_platform_sc_artifacts(
    page: Page,
    panel: Locator | None,
    result: dict[str, Any],
    *,
    artifact_prefix: str = "platform_sc",
    timeout: bool = False,
) -> dict[str, Any]:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    prefix = _safe_prefix(artifact_prefix)
    page_screenshot = DEBUG_DIR / f"{prefix}_page_{stamp}.png"
    panel_screenshot = DEBUG_DIR / f"{prefix}_panel_{stamp}.png"
    panel_html = DEBUG_DIR / f"{prefix}_panel_{stamp}.html"
    panel_text = DEBUG_DIR / f"{prefix}_text_{stamp}.txt"
    result_json = DEBUG_DIR / f"{prefix}_result_{stamp}.json"

    panel_text_value = ""
    panel_html_value = ""
    try:
        await page.screenshot(path=str(page_screenshot), full_page=True)
    except Exception:
        page_screenshot = Path("")
    if panel is not None:
        try:
            await panel.screenshot(path=str(panel_screenshot))
        except Exception:
            panel_screenshot = Path("")
        panel_text_value = await _safe_panel_text(panel)
        panel_html_value = await _safe_panel_html(panel)
    try:
        panel_text.write_text(panel_text_value, encoding="utf-8")
    except Exception:
        panel_text = Path("")
    try:
        panel_html.write_text(panel_html_value, encoding="utf-8")
    except Exception:
        panel_html = Path("")

    artifacts = {
        "page_screenshot": str(page_screenshot) if str(page_screenshot) else "",
        "panel_screenshot": str(panel_screenshot) if str(panel_screenshot) else "",
        "panel_html": str(panel_html) if str(panel_html) else "",
        "panel_text": str(panel_text) if str(panel_text) else "",
        "result_json": str(result_json),
    }

    if timeout:
        timeout_png = DEBUG_DIR / f"{prefix}_timeout_{stamp}.png"
        timeout_html = DEBUG_DIR / f"{prefix}_timeout_{stamp}.html"
        timeout_txt = DEBUG_DIR / f"{prefix}_timeout_{stamp}.txt"
        try:
            await page.screenshot(path=str(timeout_png), full_page=True)
        except Exception:
            timeout_png = Path("")
        try:
            timeout_html.write_text(panel_html_value, encoding="utf-8")
        except Exception:
            timeout_html = Path("")
        try:
            timeout_txt.write_text(panel_text_value, encoding="utf-8")
        except Exception:
            timeout_txt = Path("")
        artifacts.update(
            {
                "timeout_screenshot": str(timeout_png) if str(timeout_png) else "",
                "timeout_html": str(timeout_html) if str(timeout_html) else "",
                "timeout_text": str(timeout_txt) if str(timeout_txt) else "",
            }
        )

    payload = dict(result)
    payload["artifacts"] = artifacts
    if not payload.get("raw_text_preview") and panel_text_value:
        payload["raw_text_preview"] = text_preview(panel_text_value)
        payload["raw_text_hash"] = text_hash(panel_text_value)
    try:
        atomic_write_json(result_json, payload)
    except Exception:
        result_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _safe_prefix(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "platform_sc").strip("._")
    return cleaned or "platform_sc"



async def collect_platform_sc_safely(page, metrics=None, **kwargs):
    """Legacy-compatible facade returning (payload, merged_metrics)."""
    timeout = kwargs.get("timeout_seconds", kwargs.get("timeout", kwargs.get("platform_sc_timeout_seconds", 90)))
    try:
        result = await wait_and_extract_platform_sc(page, timeout_seconds=int(timeout or 90))
    except TypeError:
        result = await wait_and_extract_platform_sc(page, timeout=int(timeout or 90))
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
    merged = apply_platform_sc_to_metrics(metrics or {}, result)
    return result, merged
