from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field

from playwright.async_api import Page

from . import watchdog


@dataclass
class PageHealth:
    ok: bool
    ready_state: str = ""
    js_alive: bool = False
    websocket_online: bool = True
    dom_hash: str = ""
    dom_changed: bool = True
    editor_writable: bool = False
    loading_stuck: bool = False
    frozen: bool = False
    reasons: list[str] = field(default_factory=list)


async def page_healthcheck(page: Page, *, previous_dom_hash: str = "", sample_seconds: float = 2.0) -> PageHealth:
    reasons: list[str] = []
    ready_state = ""
    dom_hash = ""
    dom_changed = True
    js_alive = False
    websocket_online = True
    editor_writable = False
    loading_stuck = False
    frozen = False

    try:
        await watchdog.js_heartbeat(page, timeout=5)
        js_alive = True
    except Exception as exc:
        reasons.append(f"js_evaluate_timeout:{exc}")

    try:
        ready_state = str(await watchdog.step("page:ready_state", page.evaluate("document.readyState"), 5))
        if ready_state not in {"interactive", "complete"}:
            reasons.append(f"ready_state:{ready_state}")
    except Exception as exc:
        reasons.append(f"ready_state_failed:{exc}")

    try:
        snapshot = await watchdog.step(
            "page:dom_snapshot",
            page.evaluate(
                """() => {
                    const body = document.body ? document.body.innerText || document.body.textContent || '' : '';
                    const loading = Array.from(document.querySelectorAll('[role="progressbar"],[class*="loading" i],[class*="spinner" i]'))
                        .filter(el => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                        }).length;
                    const editor = document.querySelector('.monaco-editor, .cm-content, textarea, [contenteditable="true"], [role="textbox"]');
                    return {body: body.slice(0, 5000), loading, editor: Boolean(editor), online: navigator.onLine};
                }"""
            ),
            5,
        )
        body = str(snapshot.get("body", ""))
        dom_hash = hashlib.sha1(re.sub(r"\s+", " ", body).encode("utf-8", "ignore")).hexdigest()
        dom_changed = bool(not previous_dom_hash or dom_hash != previous_dom_hash)
        websocket_online = bool(snapshot.get("online", True))
        if not websocket_online:
            reasons.append("navigator_offline")
        loading_stuck = bool(snapshot.get("loading", 0) > 0 and not dom_changed)
        if loading_stuck:
            reasons.append("loading_indicator_without_dom_change")
        if not snapshot.get("editor"):
            reasons.append("editor_not_found")
    except Exception as exc:
        reasons.append(f"dom_probe_failed:{exc}")

    await asyncio.sleep(sample_seconds)
    try:
        second_now = await watchdog.js_heartbeat(page, timeout=5)
        frozen = not bool(second_now)
        if frozen:
            reasons.append("date_now_invalid")
    except Exception as exc:
        frozen = True
        reasons.append(f"page_frozen:{exc}")

    try:
        editor_writable = bool(
            await watchdog.step(
                "page:editor_writable_probe",
                page.evaluate(
                    """() => {
                        const visible = el => {
                            if (!el) return false;
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                        };
                        const editor = Array.from(document.querySelectorAll('.monaco-editor, .cm-content, textarea, [contenteditable="true"], [role="textbox"]')).find(visible);
                        return Boolean(editor);
                    }"""
                ),
                5,
            )
        )
        if not editor_writable:
            reasons.append("editor_not_writable")
    except Exception as exc:
        reasons.append(f"editor_probe_failed:{exc}")

    ok = js_alive and not frozen and websocket_online and not loading_stuck
    return PageHealth(
        ok=ok,
        ready_state=ready_state,
        js_alive=js_alive,
        websocket_online=websocket_online,
        dom_hash=dom_hash,
        dom_changed=dom_changed,
        editor_writable=editor_writable,
        loading_stuck=loading_stuck,
        frozen=frozen,
        reasons=reasons,
    )
