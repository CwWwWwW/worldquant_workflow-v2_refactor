from __future__ import annotations

import logging
import json
from pathlib import Path

from bs4 import BeautifulSoup

from .deepseek_client import DeepSeekClient, clean_code
from .models import TemplateItem, WorkflowConfig
from .paths import INPUT_TEMPLATE_DIR, ROOT, SPLIT_MANIFEST_FILE, TEMPLATE_DIR


def read_user_template_texts(extra_files: list[str] | None = None, inline_text: str = "") -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    has_explicit_input = bool(inline_text.strip() or extra_files)
    if inline_text.strip():
        texts.append(("cli-inline", inline_text))

    for file_path in extra_files or []:
        path = Path(file_path)
        if path.exists():
            texts.append((str(path), path.read_text(encoding="utf-8", errors="ignore")))

    if not has_explicit_input:
        for path in sorted(INPUT_TEMPLATE_DIR.glob("*")):
            if path.suffix.lower() not in {".txt", ".py", ".md"}:
                continue
            texts.append((str(path), path.read_text(encoding="utf-8", errors="ignore")))
    return texts


def normalize_max_count(max_count: int | None) -> int | None:
    return max_count if max_count and max_count > 0 else None


def normalize_raw_text(raw_text: str) -> str:
    if "<" in raw_text and ">" in raw_text:
        soup = BeautifulSoup(raw_text, "html.parser")
        return soup.get_text("\n")
    return raw_text


async def split_and_store_templates(
    ds: DeepSeekClient,
    config: WorkflowConfig,
    extra_files: list[str] | None = None,
    inline_text: str = "",
    *,
    use_existing: bool = False,
) -> list[TemplateItem]:
    if use_existing:
        items = read_last_split_template_items(config.max_templates)
        if items:
            logging.info("从上次已分割模板清单启动：count=%s", len(items))
            return items
        items = read_split_template_items(config.max_templates)
        if items:
            logging.info("未找到上次分割清单，回退读取 templates/：count=%s", len(items))
            return items
        raise RuntimeError(f"未发现已分割模板，请先执行分割或把 py/txt/md 放入 {TEMPLATE_DIR}")

    raw_sources = read_user_template_texts(extra_files, inline_text)
    if not raw_sources:
        raise RuntimeError(f"未发现用户模板文本，请把 txt/py/md 放入 {INPUT_TEMPLATE_DIR} 或使用 --template-file/--template-text")

    all_items: list[TemplateItem] = []
    max_count = normalize_max_count(config.max_templates)
    for source, raw in raw_sources:
        text = normalize_raw_text(raw)
        remaining = None if max_count is None else max_count - len(all_items)
        if remaining is not None and remaining <= 0:
            break
        logging.info("DeepSeek 开始完整文件筛选并分割模板：source=%s chars=%s", source, len(text))
        templates = await ds.split_templates(text, remaining)
        if not templates:
            raise RuntimeError(f"DeepSeek 未返回可用模板 JSON：source={source}")
        for item in templates:
            code = clean_code(str(item.get("code", "")))
            if not code:
                continue
            all_items.append(
                TemplateItem(
                    index=len(all_items) + 1,
                    name=item.get("name") or f"template_{len(all_items) + 1:03d}",
                    code=code,
                    source=source,
                )
            )
            if max_count is not None and len(all_items) >= max_count:
                break
        if max_count is not None and len(all_items) >= max_count:
            break

    if not all_items:
        raise RuntimeError("DeepSeek 未能从用户文本中筛出可用模板")

    for stale_path in TEMPLATE_DIR.glob("ds_template_*.py"):
        stale_path.unlink(missing_ok=True)
    for index, item in enumerate(all_items, start=1):
        path = TEMPLATE_DIR / f"ds_template_{index:03d}.py"
        path.write_text(item.code + "\n", encoding="utf-8")
        item.path = str(path)
        logging.info("模板已保存：%s source=%s", path, item.source)
    write_split_manifest(all_items)
    return all_items


def write_split_manifest(items: list[TemplateItem]) -> None:
    payload = {
        "templates": [
            {
                "index": item.index,
                "name": item.name,
                "path": portable_path(item.path),
                "source": portable_path(item.source, external_as_name=True),
            }
            for item in items
        ]
    }
    SPLIT_MANIFEST_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def portable_path(value: str, *, external_as_name: bool = False) -> str:
    if not value:
        return ""
    if value == "cli-inline":
        return value
    path = Path(value)
    try:
        resolved = path.resolve()
        return resolved.relative_to(ROOT).as_posix()
    except (OSError, ValueError):
        if external_as_name and path.name:
            return path.name
        return value


def resolve_manifest_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def read_last_split_template_items(max_count: int | None = None) -> list[TemplateItem]:
    if not SPLIT_MANIFEST_FILE.exists():
        return []
    try:
        data = json.loads(SPLIT_MANIFEST_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        logging.warning("上次分割清单损坏，忽略：%s", SPLIT_MANIFEST_FILE)
        return []
    paths = [
        str(item.get("path", ""))
        for item in data.get("templates", [])
        if isinstance(item, dict) and item.get("path")
    ]
    return read_split_template_items(max_count=max_count, files=paths)


def read_split_template_items(max_count: int | None = None, files: list[str] | None = None) -> list[TemplateItem]:
    max_count = normalize_max_count(max_count)
    paths: list[Path] = []
    for file_path in files or []:
        path = resolve_manifest_path(file_path)
        if path.exists() and path.suffix.lower() in {".py", ".txt", ".md"}:
            paths.append(path)
    if not paths:
        paths = [
            path
            for path in sorted(TEMPLATE_DIR.glob("*"))
            if path.suffix.lower() in {".py", ".txt", ".md"}
        ]

    items: list[TemplateItem] = []
    for path in paths:
        code = clean_code(path.read_text(encoding="utf-8", errors="ignore"))
        if not code:
            continue
        items.append(
            TemplateItem(
                index=len(items) + 1,
                name=path.stem,
                code=code,
                source=str(path),
                path=str(path),
            )
        )
        if max_count and len(items) >= max_count:
            break
    return items
