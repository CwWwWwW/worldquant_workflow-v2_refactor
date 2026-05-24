from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, TimeoutError, async_playwright

from .config import selector_config
from .models import BASE_URL, SIMULATE_URL, WorkflowConfig
from .paths import COOKIE_FILE


def system_browser(config: WorkflowConfig | None = None) -> str:
    configured = ""
    if config:
        configured = config.browser_executable_path
    configured = os.getenv("WQ_BROWSER_EXECUTABLE") or configured
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return str(path)
        logging.warning("配置的浏览器路径不存在，继续尝试系统默认路径：%s", configured)

    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


async def launch_browser(config: WorkflowConfig) -> tuple[Playwright, Browser, BrowserContext, Page]:
    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(headless=config.headless, slow_mo=config.slow_mo)
    except Exception:
        executable = system_browser(config)
        if not executable:
            raise
        logging.warning("Playwright Chromium 启动失败，回退系统浏览器：%s", executable)
        browser = await playwright.chromium.launch(
            executable_path=executable,
            headless=config.headless,
            slow_mo=config.slow_mo,
        )
    context_kwargs = {"viewport": {"width": 1920, "height": 1080}}
    if COOKIE_FILE.exists():
        context_kwargs["storage_state"] = str(COOKIE_FILE)
    context = await browser.new_context(**context_kwargs)
    try:
        await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE_URL)
    except Exception:
        logging.info("剪贴板权限授权失败，后续使用键盘输入兜底")
    page = await context.new_page()
    page.set_default_timeout(30000)
    return playwright, browser, context, page


async def close_browser(playwright: Playwright, browser: Browser, context: BrowserContext) -> None:
    try:
        await context.storage_state(path=str(COOKIE_FILE))
    except Exception:
        logging.info("Failed to persist browser storage before close", exc_info=True)
    try:
        await context.close()
    except Exception:
        logging.info("Failed to close browser context", exc_info=True)
    try:
        await browser.close()
    except Exception:
        logging.info("Failed to close browser", exc_info=True)
    try:
        await playwright.stop()
    except Exception:
        logging.info("Failed to stop Playwright", exc_info=True)


async def launch_playwright_browser(config: WorkflowConfig) -> tuple[Playwright, Browser]:
    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(headless=config.headless, slow_mo=config.slow_mo)
    except Exception:
        executable = system_browser(config)
        if not executable:
            await playwright.stop()
            raise
        logging.warning("Playwright Chromium launch failed; falling back to system browser: %s", executable)
        browser = await playwright.chromium.launch(
            executable_path=executable,
            headless=config.headless,
            slow_mo=config.slow_mo,
        )
    return playwright, browser


def alpha_context_kwargs() -> dict[str, object]:
    context_kwargs: dict[str, object] = {"viewport": {"width": 1920, "height": 1080}}
    if COOKIE_FILE.exists():
        context_kwargs["storage_state"] = str(COOKIE_FILE)
    return context_kwargs


async def new_alpha_context(browser: Browser, config: WorkflowConfig) -> tuple[BrowserContext, Page]:
    context = await browser.new_context(**alpha_context_kwargs())
    try:
        await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE_URL)
    except Exception:
        logging.info("Clipboard permission grant failed; keyboard input fallback remains available")
    page = await context.new_page()
    page.set_default_timeout(30000)
    return context, page


async def close_context_safe(context: BrowserContext | None, *, persist_storage: bool = False) -> None:
    if context is None:
        return
    try:
        if persist_storage:
            await context.storage_state(path=str(COOKIE_FILE))
    except Exception:
        logging.info("Failed to persist context storage before closing")
    try:
        await context.close()
    except Exception:
        logging.info("Failed to close browser context")


def merged_selector_config(config: WorkflowConfig, name: str, defaults: list[str]) -> list[str]:
    configured = config.selectors.get(name)
    selectors: list[str] = []
    if isinstance(configured, list):
        selectors.extend(str(item) for item in configured if str(item).strip())
    selectors.extend(defaults)
    return list(dict.fromkeys(selectors))


async def wait_visible_any(page: Page, selectors: list[str], timeout: int = 15000) -> str:
    last: Exception | None = None
    for selector in selectors:
        try:
            await page.wait_for_selector(selector, state="visible", timeout=timeout)
            return selector
        except TimeoutError as exc:
            last = exc
    raise TimeoutError(f"未找到可见元素：{selectors}") from last


async def goto_page(page: Page, url: str, *, timeout: int = 60000, retries: int = 2) -> None:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception as exc:
            last = exc
            logging.warning("页面导航失败 attempt=%s url=%s error=%s", attempt + 1, url, exc)
            if page.url.startswith(url):
                return
            if attempt < retries:
                await asyncio.sleep(2)
                continue
            try:
                await page.goto(url, wait_until="commit", timeout=timeout)
                await page.wait_for_selector("body", state="visible", timeout=timeout)
                return
            except Exception as fallback_exc:
                last = fallback_exc
    raise RuntimeError(f"页面导航连续失败：{url}") from last


async def safe_click(page: Page, selectors: list[str], label: str, timeout: int = 15000) -> None:
    selector = await wait_visible_any(page, selectors, timeout)
    if re.search(r"\bsubmit\b|提交", f"{label} {selector}", re.I) and not re.search(r"login|sign in|登录", label, re.I):
        raise RuntimeError(f"禁止点击 Submit/提交 控件：{label} {selector}")
    locator = page.locator(selector).first
    try:
        await locator.click(timeout=timeout)
    except Exception:
        try:
            await locator.click(timeout=5000, force=True)
        except Exception:
            await locator.evaluate("el => el.click()")
    logging.info("网页点击：%s selector=%s", label, selector)


async def fill_any(page: Page, selectors: list[str], value: str, label: str, timeout: int = 15000) -> None:
    selector = await wait_visible_any(page, selectors, timeout)
    locator = page.locator(selector).first
    await locator.click()
    await locator.fill(value)
    logging.info("网页填写：%s selector=%s", label, selector)


async def set_editor_text(page: Page, selectors: list[str], code: str) -> None:
    method = await try_set_editor_model_text(page, code)
    if method:
        await asyncio.sleep(0.5)
        current = await read_editor_text(page)
        if editor_text_matches(current, code):
            logging.info("编辑器写入成功：%s", method)
            return
        logging.warning("编辑器模型写入校验失败，切换键盘回退：%s", method)

    preferred = [
        ".monaco-editor textarea.inputarea",
        "textarea.inputarea",
        '.monaco-editor [role="textbox"]',
        ".monaco-editor",
        ".cm-editor",
        ".cm-content",
        '[contenteditable="true"]',
        '[role="textbox"]',
    ]
    ordered_selectors = list(dict.fromkeys(preferred + selectors))
    selector = await wait_visible_any(page, ordered_selectors, timeout=30000)
    locator = page.locator(selector).first
    try:
        await locator.click(timeout=5000, force=True)
    except Exception:
        await locator.evaluate("el => el.focus()")

    tag = await locator.evaluate("el => el.tagName.toLowerCase()")
    editable = await locator.evaluate("el => el.isContentEditable")
    class_name = await locator.evaluate("el => String(el.className || '')")
    if tag == "textarea" and "inputarea" in class_name:
        monaco = page.locator(".monaco-editor").first
        await monaco.click(position={"x": 120, "y": 30}, force=True, timeout=5000)
        await page.keyboard.press("Control+Home")
        await page.keyboard.press("Control+Shift+End")
        await page.keyboard.press("Backspace")
        await paste_text(page, code)
        current = await read_editor_text(page)
        if editor_text_matches(current, code):
            logging.info("编辑器写入成功：%s", selector)
            return
        await page.keyboard.press("Control+Home")
        await page.keyboard.press("Control+Shift+End")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(code)
        current = await read_editor_text(page)
        if editor_text_matches(current, code):
            logging.info("编辑器写入成功：%s insert_text_retry", selector)
            return
    if tag in {"textarea", "input"}:
        try:
            await locator.fill(code)
            current = await read_editor_text(page)
            if editor_text_matches(current, code):
                logging.info("编辑器写入成功：%s", selector)
                return
        except Exception:
            pass
    if editable:
        await locator.evaluate(
            """(el, value) => {
                el.innerText = value;
                el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
            }""",
            code,
        )
        current = await read_editor_text(page)
        if editor_text_matches(current, code):
            logging.info("编辑器写入成功：%s", selector)
            return
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Backspace")
    await paste_text(page, code)
    current = await read_editor_text(page)
    if not editor_text_matches(current, code):
        logging.error("编辑器写入校验失败 actual=%r expected=%r", current[:800], code[:800])
        raise RuntimeError("编辑器写入后校验失败，页面内部代码没有更新")
    logging.info("编辑器写入成功：keyboard fallback")


async def try_set_editor_model_text(page: Page, code: str) -> str:
    try:
        return await page.evaluate(
            """(value) => {
                const visible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const fire = (el) => {
                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertFromPaste', data: value}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                };
                if (window.monaco && window.monaco.editor && window.monaco.editor.getModels) {
                    const models = window.monaco.editor.getModels();
                    if (models.length) {
                        models[models.length - 1].setValue(value);
                        return 'monaco.model';
                    }
                }
                for (const node of Array.from(document.querySelectorAll('.CodeMirror'))) {
                    if (node.CodeMirror) {
                        node.CodeMirror.setValue(value);
                        return 'codemirror5';
                    }
                }
                const cm6 = Array.from(document.querySelectorAll('.cm-content[contenteditable="true"]')).find(visible);
                const view = cm6 && cm6.cmView && cm6.cmView.view;
                if (view && view.dispatch && view.state && view.state.doc) {
                    view.dispatch({changes: {from: 0, to: view.state.doc.length, insert: value}});
                    return 'codemirror6';
                }
                const editable = Array.from(document.querySelectorAll('[contenteditable="true"]')).find(visible);
                if (editable) {
                    editable.innerText = value;
                    fire(editable);
                    return 'contenteditable';
                }
                return '';
            }""",
            code,
        )
    except Exception:
        return ""


async def paste_text(page: Page, text: str) -> None:
    try:
        await page.evaluate(
            """value => Promise.race([
                navigator.clipboard.writeText(value),
                new Promise((_, reject) => setTimeout(() => reject(new Error('clipboard write timeout')), 1500))
            ])""",
            text,
        )
        await page.keyboard.press("Control+V")
    except Exception:
        await page.keyboard.insert_text(text)


async def read_editor_text(page: Page) -> str:
    clipboard_text = await read_editor_text_from_clipboard(page)
    if clipboard_text.strip():
        return clipboard_text
    try:
        return await page.evaluate(
            """() => {
                if (window.monaco && window.monaco.editor && window.monaco.editor.getModels) {
                    const models = window.monaco.editor.getModels();
                    if (models.length) return models[models.length - 1].getValue() || '';
                }
                for (const node of Array.from(document.querySelectorAll('.CodeMirror'))) {
                    if (node.CodeMirror) return node.CodeMirror.getValue() || '';
                }
                const cm6 = document.querySelector('.cm-content[contenteditable="true"]');
                const view = cm6 && cm6.cmView && cm6.cmView.view;
                if (view && view.state && view.state.doc) return view.state.doc.toString();
                const values = [];
                for (const el of Array.from(document.querySelectorAll('textarea,input,[contenteditable="true"],[role="textbox"]'))) {
                    const text = el.value || el.innerText || el.textContent || '';
                    if (text.trim()) values.push(text);
                }
                values.sort((a, b) => b.length - a.length);
                return values[0] || '';
            }"""
        )
    except Exception:
        return ""


async def read_editor_text_from_clipboard(page: Page) -> str:
    try:
        monaco = page.locator(".monaco-editor").first
        if not await monaco.is_visible(timeout=500):
            return ""
        await monaco.click(position={"x": 120, "y": 30}, force=True, timeout=1500)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Control+C")
        await asyncio.sleep(0.2)
        text = await page.evaluate(
            """() => Promise.race([
                navigator.clipboard.readText(),
                new Promise((_, reject) => setTimeout(() => reject(new Error('clipboard read timeout')), 1500))
            ])"""
        )
        return text or ""
    except Exception:
        return ""


def editor_text_matches(actual: str, expected: str) -> bool:
    actual_norm = normalize_editor_text(actual)
    expected_norm = normalize_editor_text(expected)
    return bool(expected_norm and actual_norm == expected_norm)


def normalize_editor_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


async def login(page: Page, context: BrowserContext, config: WorkflowConfig) -> None:
    await ensure_authenticated(page, config, target_url=SIMULATE_URL, context=context)


async def ensure_authenticated(
    page: Page,
    config: WorkflowConfig,
    *,
    target_url: str = SIMULATE_URL,
    context: BrowserContext | None = None,
) -> None:
    await goto_page(page, target_url)
    await asyncio.sleep(2)
    reauthenticated = await ensure_authenticated_if_needed(
        page,
        config,
        target_url=target_url,
        context=context,
        stage="entry",
    )
    if not reauthenticated:
        logging.info("已通过 cookie 进入 WorldQuant")
        return
    logging.info("登录态确认完成：%s", target_url)


async def ensure_authenticated_if_needed(
    page: Page,
    config: WorkflowConfig,
    *,
    target_url: str = SIMULATE_URL,
    context: BrowserContext | None = None,
    stage: str = "",
    current_body: str | None = None,
) -> bool:
    active_context = context or page.context
    body = current_body
    if body is None:
        try:
            body = await page.locator("body").inner_text(timeout=10000)
        except Exception:
            body = ""
    reason = read_auth_block_reason(page.url, body or "")
    if not reason:
        return False

    logging.warning(
        "检测到登录态失效：stage=%s url=%s reason=%s；清理旧 cookie 后自动重新登录",
        stage or "unknown",
        page.url,
        reason,
    )
    await clear_stale_auth_state(active_context)
    await perform_login(page, active_context, config)
    await goto_page(page, target_url)
    await asyncio.sleep(2)
    try:
        body = await page.locator("body").inner_text(timeout=10000)
    except Exception:
        body = ""
    post_reason = read_auth_block_reason(page.url, body or "")
    if post_reason:
        raise RuntimeError(f"重新登录后仍停留在认证阻断页面：{post_reason}；请检查账号密码、验证码或平台会话状态")
    logging.info("登录态恢复完成：stage=%s target=%s", stage or "unknown", target_url)
    return True


async def clear_stale_auth_state(context: BrowserContext) -> None:
    try:
        await context.clear_cookies()
    except Exception:
        logging.info("清理浏览器 cookie 失败，继续尝试登录")
    try:
        COOKIE_FILE.unlink(missing_ok=True)
        logging.info("已删除过期 cookies.json")
    except Exception:
        logging.info("删除 cookies.json 失败，继续尝试登录")


async def perform_login(page: Page, context: BrowserContext, config: WorkflowConfig) -> None:
    if not config.email or not config.password:
        raise RuntimeError("缺少 WorldQuant 账号密码，请设置 WORLDQUANT_EMAIL/WORLDQUANT_PASSWORD 或 config.json")

    await goto_page(page, config.login_url)
    await asyncio.sleep(1)
    body = await page.locator("body").inner_text(timeout=10000)
    if not is_auth_blocking_page(page.url, body):
        await goto_page(page, f"{BASE_URL}/sign-in")
    email_selectors = merged_selector_config(
        config,
        "login_email",
        [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
            'input[autocomplete="username"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="邮箱" i]',
            'input[type="text"]',
        ],
    )
    password_selectors = merged_selector_config(
        config,
        "login_password",
        ['input[type="password"]', 'input[name="password"]', 'input[autocomplete="current-password"]'],
    )
    submit_selectors = merged_selector_config(
        config,
        "login_submit",
        [
            'button[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Log in")',
            'button:has-text("Sign in")',
            'button:has-text("Sign In")',
            'button:has-text("登录")',
            'input[type="submit"]',
        ],
    )
    await fill_any(page, email_selectors, config.email, "登录邮箱")
    await fill_any(page, password_selectors, config.password, "登录密码")
    await safe_click(page, submit_selectors, "登录")
    await asyncio.sleep(3)

    body = await page.locator("body").inner_text(timeout=10000)
    if re.search(r"captcha|verify|human|challenge|验证码|人机", body, re.I):
        print("\n检测到验证码/人机验证。请在浏览器中完成，脚本会自动检测登录状态并继续。", flush=True)
    await wait_until_logged_in(page, config)
    await context.storage_state(path=str(COOKIE_FILE))
    logging.info("登录成功，cookie 已保存")


async def wait_until_logged_in(page: Page, config: WorkflowConfig, timeout_seconds: int = 600) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        try:
            body = await page.locator("body").inner_text(timeout=5000)
            if not re.search(r"captcha|verify|human|challenge|验证码|人机", body, re.I) and not is_signin_page(page.url, body):
                return
            if page.url.rstrip("/") != config.login_url.rstrip("/") and not is_signin_page(page.url, body):
                return
        except Exception:
            pass
        await asyncio.sleep(3)
    raise RuntimeError("等待人工验证/登录完成超时")


def is_signin_page(url: str, body: str) -> bool:
    if re.search(r"/sign-?in|/login", url, re.I):
        return True
    has_email = bool(re.search(r"\bEmail\b|邮箱", body, re.I))
    has_password = bool(re.search(r"\bPassword\b|密码", body, re.I))
    has_signin = bool(re.search(r"\bSign In\b|\bLog In\b|登录", body, re.I))
    return has_signin and has_email and has_password


def is_auth_blocking_page(url: str, body: str) -> bool:
    return bool(read_auth_block_reason(url, body))


def read_auth_block_reason(url: str, body: str) -> str:
    if is_signin_page(url, body):
        return "signin_page"
    compact = re.sub(r"\s+", " ", body or "").strip()
    if not compact:
        return ""
    session_hint = re.search(
        r"your session has expired|session expired|please\s+(?:log|sign)\s+in|authentication required",
        compact,
        re.I,
    )
    auth_hint = re.search(
        r"your session has expired|session expired|please\s+(?:log|sign)\s+in|authentication required|unauthorized|not authorized|forgot password|remember me|continue with|验证码|人机验证",
        compact,
        re.I,
    )
    form_hint = re.search(r"\bEmail\b|邮箱|Username|\bPassword\b|密码|\bSign In\b|\bLog In\b|登录", compact, re.I)
    if auth_hint and form_hint:
        return auth_hint.group(0)
    if session_hint:
        return session_hint.group(0)
    return ""
