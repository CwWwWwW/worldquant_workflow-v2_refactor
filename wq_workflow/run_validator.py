from __future__ import annotations

import re
import time

from playwright.async_api import Page

from .models import RunValidation


class RunValidationError(RuntimeError):
    pass


RUN_NOT_TRIGGERED = "RUN_NOT_TRIGGERED"
STALE_RESULT = "STALE_RESULT"


_STATIC_ID_TOKENS = {
    "asset",
    "assets",
    "bundle",
    "chunk",
    "chunks",
    "css",
    "dist",
    "font",
    "fonts",
    "image",
    "images",
    "img",
    "index",
    "js",
    "main",
    "media",
    "runtime",
    "scrsrc",
    "static",
    "style",
    "styles",
    "vendor",
}


def is_plausible_simulation_id(value: object, source: str = "") -> bool:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,80}", text):
        return False

    lowered = text.lower().strip("_-")
    source_lowered = (source or "").lower()
    if lowered in _STATIC_ID_TOKENS:
        return False
    if any(token in lowered for token in ["scrsrc", "webpack", "vite", "favicon"]):
        return False
    if re.search(r"\.(?:js|css|png|jpg|jpeg|svg|woff2?|map)$", lowered):
        return False
    if source_lowered.startswith("resource") and "path" in source_lowered and not re.search(r"\d", lowered):
        return False
    return True


async def read_simulation_id(page: Page) -> str:
    try:
        raw_candidates = await page.evaluate(
            """() => {
                const candidates = [];
                const push = (value, source) => {
                    if (value === undefined || value === null) return;
                    const text = String(value).trim();
                    if (text) candidates.push({value: text, source});
                };
                const pushUrlIds = (rawUrl, sourcePrefix) => {
                    const raw = String(rawUrl || '');
                    if (!raw) return;
                    try {
                        const url = new URL(raw, window.location.origin);
                        for (const key of ['simulationId', 'alphaId', 'runId']) {
                            push(url.searchParams.get(key), `${sourcePrefix}:query:${key}`);
                        }
                        const path = url.pathname || '';
                        for (const re of [
                            /\\/(?:simulations|simulation|backtests|runs)\\/([A-Za-z0-9_-]{6,80})(?:[\\/?#]|$)/i,
                            /\\/(?:alphas|alpha)\\/([A-Za-z0-9_-]{6,80})(?:[\\/?#]|$)/i
                        ]) {
                            const match = path.match(re);
                            if (match) push(match[1], `${sourcePrefix}:path`);
                        }
                    } catch (_) {
                        for (const re of [
                            /(?:simulationId|alphaId|runId)=([A-Za-z0-9_-]{6,80})/i,
                            /\\/(?:simulations|simulation|backtests|runs|alphas|alpha)\\/([A-Za-z0-9_-]{6,80})(?:[\\/?#]|$)/i
                        ]) {
                            const match = raw.match(re);
                            if (match) push(match[1], `${sourcePrefix}:raw`);
                        }
                    }
                };
                push(window.__WQ_SIMULATION_ID, 'window.__WQ_SIMULATION_ID');
                push(window.simulationId, 'window.simulationId');
                push(window.currentSimulationId, 'window.currentSimulationId');
                pushUrlIds(window.location.href, 'location');
                for (const entry of performance.getEntriesByType('resource').slice(-300)) {
                    const url = String(entry.name || '');
                    pushUrlIds(url, 'resource');
                }
                for (const el of Array.from(document.querySelectorAll('[data-simulation-id],[data-alpha-id],[data-id]')).slice(0, 200)) {
                    push(el.getAttribute('data-simulation-id'), 'data-simulation-id');
                    push(el.getAttribute('data-alpha-id'), 'data-alpha-id');
                    push(el.getAttribute('data-id'), 'data-id');
                }
                const text = document.body ? document.body.innerText || document.body.textContent || '' : '';
                for (const re of [
                    /Simulation\\s*ID\\s*[:#]?\\s*([A-Za-z0-9_-]{6,80})/i,
                    /Alpha\\s*ID\\s*[:#]?\\s*([A-Za-z0-9_-]{6,80})/i,
                    /Run\\s*ID\\s*[:#]?\\s*([A-Za-z0-9_-]{6,80})/i,
                    /Last\\s+Run\\s*ID\\s*[:#]?\\s*([A-Za-z0-9_-]{6,80})/i
                ]) {
                    const m = text.match(re);
                    if (m) push(m[1], 'body');
                }
                return candidates;
            }"""
        )
        if isinstance(raw_candidates, str):
            return raw_candidates if is_plausible_simulation_id(raw_candidates) else ""
        if not isinstance(raw_candidates, list):
            return ""
        for candidate in raw_candidates:
            if isinstance(candidate, dict):
                value = str(candidate.get("value") or "").strip()
                source = str(candidate.get("source") or "")
            else:
                value = str(candidate or "").strip()
                source = ""
            if is_plausible_simulation_id(value, source):
                return value
        return ""
    except Exception:
        return ""


async def read_result_timestamp(page: Page) -> float | None:
    try:
        value = await page.evaluate(
            """() => {
                const text = document.body ? document.body.innerText || document.body.textContent || '' : '';
                const patterns = [
                    /Last\\s+Run\\s*[:#]?\\s*([^\\n]+)/i,
                    /Last\\s+saved\\s+([^\\n]+)/i,
                    /Completed\\s+at\\s+([^\\n]+)/i,
                    /Updated\\s+at\\s+([^\\n]+)/i
                ];
                for (const pattern of patterns) {
                    const match = text.match(pattern);
                    if (!match) continue;
                    const parsed = Date.parse(match[1]);
                    if (!Number.isNaN(parsed)) return parsed / 1000;
                }
                const times = Array.from(document.querySelectorAll('time[datetime]')).map(el => Date.parse(el.getAttribute('datetime')));
                const valid = times.filter(value => !Number.isNaN(value));
                if (valid.length) return Math.max(...valid) / 1000;
                return null;
            }"""
        )
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


async def read_result_freshness_token(page: Page) -> str:
    simulation_id = await read_simulation_id(page)
    timestamp = await read_result_timestamp(page)
    try:
        text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        text = ""
    metrics = []
    for label in ["Sharpe", "Fitness", "Turnover", "Returns", "Drawdown", "Margin"]:
        match = re.search(rf"\b{label}\b[^\d-]*(-?\d+(?:\.\d+)?%?)", text, re.I)
        if match:
            metrics.append(f"{label}:{match.group(1)}")
    return "|".join([simulation_id, str(timestamp or ""), *metrics])


async def validate_run_triggered(
    page: Page,
    *,
    old_simulation_id: str,
    click_timestamp: float,
    timeout: float = 45.0,
) -> RunValidation:
    deadline = time.monotonic() + timeout
    last_id = ""
    while time.monotonic() < deadline:
        new_id = await read_simulation_id(page)
        last_id = new_id or last_id
        if new_id and new_id != old_simulation_id:
            return RunValidation(
                ok=True,
                old_simulation_id=old_simulation_id,
                new_simulation_id=new_id,
                click_timestamp=click_timestamp,
            )
        await page.wait_for_timeout(1000)
    return RunValidation(
        ok=False,
        old_simulation_id=old_simulation_id,
        new_simulation_id=last_id,
        click_timestamp=click_timestamp,
        reason=RUN_NOT_TRIGGERED,
    )


async def validate_result_freshness(page: Page, validation: RunValidation) -> RunValidation:
    result_timestamp = await read_result_timestamp(page)
    validation.result_timestamp = result_timestamp
    validation.timestamp_fresh = bool(result_timestamp is not None and result_timestamp > validation.click_timestamp)
    if validation.consistency_signals_present:
        score = 0
        if validation.progress_complete:
            score += 40
        if validation.metrics_detected:
            score += 20
        if validation.fingerprint_stable:
            score += 30
        if validation.timestamp_fresh:
            score += 10
        validation.freshness_score = score
        if score < validation.freshness_accept_score:
            validation.ok = False
            validation.reason = STALE_RESULT
        return validation
    if result_timestamp is None:
        validation.ok = False
        validation.reason = STALE_RESULT
    elif result_timestamp <= validation.click_timestamp:
        validation.ok = False
        validation.reason = STALE_RESULT
    return validation
