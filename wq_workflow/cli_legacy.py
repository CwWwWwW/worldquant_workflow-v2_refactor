from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import locale
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import load_config
from .paths import (
    CONFIG_FILE,
    FAVORITE_LOG_FILE,
    INPUT_TEMPLATE_DIR,
    ITERATION_LOG_FILE,
    LOG_DIR,
    ROOT,
    SPLIT_MANIFEST_FILE,
    TEMPLATE_DIR,
    WORKFLOW_LOG_FILE,
    ensure_runtime_files,
)
from .templates import read_last_split_template_items, read_split_template_items


PID_FILE = LOG_DIR / "workflow_active.pid"
COMMANDS = {"run", "split", "status", "init", "menu", "help", "-h", "--help"}


def main(argv: list[str] | None = None) -> int:
    configure_console()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return menu_command()

    command = args[0].lower()
    if command == "menu":
        return menu_command()
    if command == "run":
        return run_command(args[1:], guided=False)
    if command == "split":
        return split_command(args[1:])
    if command == "status":
        return status_command()
    if command == "init":
        return init_command()
    if command in {"help", "-h", "--help"}:
        print_help()
        return 0
    return run_command(args, guided=False)


def configure_console() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if os.name == "nt":
        try:
            subprocess.run(["chcp", "65001"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass


def menu_command() -> int:
    ensure_runtime_files()
    print_banner()
    while True:
        try:
            print()
            print("主菜单")
            print("  1. 启动工作流")
            print("  2. 分割模板")
            print("  3. 配置账号/API Key")
            print("  4. 状态与日志")
            print("  5. 导出日志")
            print("  6. 导入日志")
            print("  0. 退出")
            choice = input("请选择：").strip()
            if choice == "1":
                workflow_menu()
            elif choice == "2":
                split_menu()
            elif choice == "3":
                ensure_config_ready(force_prompt=True)
            elif choice == "4":
                status_command()
            elif choice == "5":
                log_export_menu()
            elif choice == "6":
                log_import_menu()
            elif choice == "0":
                print("已退出。")
                return 0
            else:
                print("请输入 0-6。")
        except KeyboardInterrupt:
            print("\n已取消当前操作；CLI 仍保持打开。若要退出，请选择 0 或直接关闭窗口。")
        except Exception as exc:
            print(f"操作失败：{exc}")
            print("CLI 已保持打开，可继续选择菜单。")


def workflow_menu() -> int:
    ensure_config_ready(force_prompt=False)
    print()
    print("启动方式")
    print("  1. 使用已分割模板（推荐）")
    print("  2. 先分割原始文本，再启动")
    choice = input("请选择：").strip() or "1"
    max_templates = input("本次最多处理模板数（留空=配置默认）：").strip()
    args: list[str] = []
    if max_templates:
        args.extend(["--max-templates", max_templates])

    if choice == "1":
        ensure_split_templates_available()
        args.append("--use-split")
    elif choice == "2":
        template_file = choose_raw_template_file()
        if template_file:
            args.extend(["--template-file", template_file])
    else:
        raise RuntimeError("启动方式无效")
    return run_command(args, guided=False)


def split_menu() -> int:
    ensure_config_ready(force_prompt=False)
    template_file = choose_raw_template_file()
    args: list[str] = []
    if template_file:
        args.extend(["--template-file", template_file])
    max_templates = input("最多分割模板数（留空=配置默认）：").strip()
    if max_templates:
        args.extend(["--max-templates", max_templates])
    return split_command(args)


def log_export_menu() -> int:
    ensure_runtime_files()
    print()
    print("日志导出")
    output_dir = resolve_project_path(input("导出目录（留空=log_exports）：").strip() or "log_exports")
    archive_choice = input("归档格式：1=zip（默认），2=tar.gz，3=不归档：").strip()
    archive_format = {"1": "zip", "2": "tar.gz", "3": ""}.get(archive_choice or "1", "zip")
    alpha_id = input("按 alpha_id 过滤（留空=不过滤）：").strip() or None
    since = input("开始时间 since，例如 2026-05-08T00:00:00（留空=不限）：").strip() or None
    until = input("结束时间 until，例如 2026-05-08T23:59:59（留空=不限）：").strip() or None
    task_id = input("按 task_id 过滤（留空=不过滤）：").strip() or None
    worker_id = input("按 worker_id 过滤（留空=不过滤）：").strip() or None

    try:
        from log_manager import export_logs

        result = export_logs(
            ROOT,
            output_dir,
            since=since,
            until=until,
            task_id=task_id,
            alpha_id=alpha_id,
            worker_id=worker_id,
            archive_format=archive_format,
            resume=True,
        )
    except Exception as exc:
        print(f"日志导出失败：{exc}")
        return 1

    print("日志导出完成。")
    print(f"Export ID：{result.export_id}")
    print(f"导出目录：{result.export_dir}")
    print(f"Manifest：{result.manifest_path}")
    print(f"文件数：{result.files_count}")
    print(f"总大小：{format_bytes(result.total_bytes)}")
    if result.archive_paths:
        print("归档文件：")
        for path in result.archive_paths:
            print(f"  {path}")
    else:
        print("归档文件：未生成")
    if result.warnings:
        print("警告：")
        for warning in result.warnings:
            print(f"  - {warning}")
    return 0


def log_import_menu() -> int:
    ensure_runtime_files()
    print()
    print("日志导入")
    source_text = input("请输入 export 目录或 zip/tar.gz/part001 路径：").strip().strip('"')
    if not source_text:
        print("未提供导入来源。")
        return 1
    source = resolve_project_path(source_text)
    mode_choice = input("导入模式：1=offline（默认），2=replay，3=incremental，4=restore：").strip()
    mode = {"1": "offline", "2": "replay", "3": "incremental", "4": "restore"}.get(mode_choice or "1", "offline")
    if mode == "restore":
        confirm = input("restore 会尝试覆盖当前日志；输入 RESTORE 确认：").strip()
        if confirm != "RESTORE":
            print("已取消 restore 导入。")
            return 0

    try:
        from log_manager import import_logs

        result = import_logs(source, ROOT, mode=mode, resume=True, conflict_policy="keep_existing")
    except Exception as exc:
        print(f"日志导入失败：{exc}")
        return 1

    print("日志导入完成。")
    print(f"模式：{result.mode}")
    print(f"目标目录：{result.target_dir}")
    print(f"导入文件数：{len(result.imported_files)}")
    print(f"跳过文件数：{len(result.skipped_files)}")
    if result.imported_files:
        print("导入文件：")
        for path in result.imported_files[:20]:
            print(f"  {path}")
        if len(result.imported_files) > 20:
            print(f"  ... 还有 {len(result.imported_files) - 20} 个")
    if result.warnings:
        print("警告：")
        for warning in result.warnings:
            print(f"  - {warning}")
    if result.errors:
        print("错误：")
        for error in result.errors:
            print(f"  - {error}")
        return 1
    return 0


def run_command(argv: list[str], *, guided: bool) -> int:
    parser = run_parser("python worldquant_auto_workflow.py run")
    options = parser.parse_args(argv)
    if guided:
        ensure_config_ready(force_prompt=False)

    ensure_runtime_files()
    running_pid = read_pid()
    if running_pid and is_process_running(running_pid) and running_pid != os.getpid():
        print(f"已有工作流正在运行：PID {running_pid}")
        print("如需结束，请人工关闭对应 CLI 窗口/进程。")
        return 1
    if running_pid and not is_process_running(running_pid):
        clear_pid_file(force=True)

    print_banner()
    print("日志会同步输出到控制台和 workflow.log。")
    print("如需结束流程，请人工关闭对应 CLI 窗口/进程。")
    print(f"主日志：{WORKFLOW_LOG_FILE}")
    print()

    write_pid_file()
    try:
        from .app.bootstrap import run as bootstrap_run

        return bootstrap_run(build_orchestrator_args(options))
    except KeyboardInterrupt:
        print("\n已收到 Ctrl+C；当前前台动作已取消，未主动结束进程链。")
        return 130
    finally:
        clear_pid_file(force=True)


def split_command(argv: list[str]) -> int:
    parser = run_parser("python worldquant_auto_workflow.py split")
    options = parser.parse_args(argv)
    options.split_only = True
    ensure_runtime_files()
    print_banner()
    print("仅执行 DeepSeek 模板分割；不会启动浏览器。")
    write_pid_file()
    try:
        from .app.bootstrap import run as bootstrap_run

        return bootstrap_run(build_orchestrator_args(options))
    except KeyboardInterrupt:
        print("\n已取消模板分割。")
        return 130
    finally:
        clear_pid_file(force=True)


def run_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="WorldQuant + DeepSeek 自动迭代工作流")
    parser.add_argument("--template-file", action="append", default=[], help="包含一个或多个模板的 txt/py/md 文件，可重复传入")
    parser.add_argument("--template-text", default="", help="直接传入模板混合文本")
    parser.add_argument("--max-templates", type=int, default=None, help="本次最多处理模板数；0 表示不限制")
    parser.add_argument("--max-iterations", type=int, default=None, help="覆盖单模板最大主循环次数；0 表示不限制")
    parser.add_argument("--use-split", action="store_true", help="从 templates/ 已分割模板启动")
    parser.add_argument("--split-only", action="store_true", help=argparse.SUPPRESS)
    return parser


def build_orchestrator_args(options: argparse.Namespace) -> list[str]:
    args: list[str] = []
    for path in options.template_file:
        args.extend(["--template-file", path])
    if options.template_text:
        args.extend(["--template-text", options.template_text])
    if options.max_templates is not None:
        args.extend(["--max-templates", str(options.max_templates)])
    if options.max_iterations is not None:
        args.extend(["--max-iterations", str(options.max_iterations)])
    if getattr(options, "use_split", False):
        args.append("--use-split")
    if getattr(options, "split_only", False):
        args.append("--split-only")
    return args


def ensure_config_ready(*, force_prompt: bool) -> None:
    config = load_config()
    missing = []
    if not config.email:
        missing.append("WorldQuant 邮箱")
    if not config.password:
        missing.append("WorldQuant 密码")
    if not config.deepseek_api_key:
        missing.append("DeepSeek API Key")
    if not force_prompt and not missing:
        print("配置检查：账号、密码和 DeepSeek API Key 已就绪。")
        return

    if missing:
        print("配置检查：缺少 " + "、".join(missing))
    print("输入新值会保存到 config.json；直接回车表示保留原值。")
    raw = read_config_json()
    deepseek = raw.get("deepseek") if isinstance(raw.get("deepseek"), dict) else {}
    raw["deepseek"] = deepseek

    email = input_value("WorldQuant 邮箱", raw.get("email") or config.email)
    if email:
        raw["email"] = email

    password = secret_value("WorldQuant 密码", raw.get("password") or config.password)
    if password:
        raw["password"] = password

    api_key = secret_value("DeepSeek API Key", deepseek.get("api_key") or config.deepseek_api_key)
    if api_key:
        deepseek["api_key"] = api_key

    model = input_value("DeepSeek 模型", deepseek.get("model") or config.deepseek_model or "deepseek-v4-pro")
    deepseek["model"] = model or "deepseek-v4-pro"
    raw.setdefault("login_url", "https://platform.worldquantbrain.com/login")
    raw.setdefault("headless", False)
    write_config_json(raw)
    print(f"配置已更新：{CONFIG_FILE}")


def input_value(label: str, current: str = "") -> str:
    shown = current if current else "未设置"
    value = input(f"{label}（当前：{shown}）：").strip()
    return value or current


def resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def format_bytes(value: int | float) -> str:
    size = float(value or 0)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{int(size)}B" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def secret_value(label: str, current: str = "") -> str:
    shown = "已设置" if current else "未设置"
    value = getpass.getpass(f"{label}（当前：{shown}，输入不回显）：").strip()
    return value or current


def choose_raw_template_file() -> str:
    existing = [
        path
        for path in sorted(INPUT_TEMPLATE_DIR.glob("*"))
        if path.suffix.lower() in {".txt", ".py", ".md"}
    ]
    print()
    if existing:
        print("检测到原始模板文件：")
        for index, path in enumerate(existing, start=1):
            print(f"  {index}. {path}")
        print("  0. 手动输入其他路径")
        choice = input("请选择原始模板文件（留空=第 1 个）：").strip()
        if not choice:
            return str(existing[0])
        if choice.isdigit() and 0 < int(choice) <= len(existing):
            return str(existing[int(choice) - 1])
        path = Path(choice.strip('"'))
        if path.exists():
            if path.suffix.lower() not in {".txt", ".py", ".md"}:
                raise RuntimeError("只支持 txt/py/md 原始模板文件")
            return str(path)

    path_text = input("请输入原始模板文件路径：").strip().strip('"')
    if not path_text:
        raise RuntimeError("未提供原始模板文件")
    path = Path(path_text)
    if not path.exists():
        raise RuntimeError(f"模板文件不存在：{path}")
    if path.suffix.lower() not in {".txt", ".py", ".md"}:
        raise RuntimeError("只支持 txt/py/md 原始模板文件")
    return str(path)


def ensure_split_templates_available() -> None:
    items = read_last_split_template_items()
    if items:
        print(f"已检测到上次分割模板：{len(items)} 个")
        print(f"清单：{SPLIT_MANIFEST_FILE}")
        return
    items = read_split_template_items()
    if items:
        print(f"检测到 templates/ 下模板：{len(items)} 个")
        print(f"目录：{TEMPLATE_DIR}")
        return
    raise RuntimeError("未发现已分割模板，请先选择“分割模板”。")


def init_command() -> int:
    ensure_runtime_files()
    if not CONFIG_FILE.exists():
        write_config_json(default_config())
        print(f"已创建配置模板：{CONFIG_FILE}")
    else:
        print(f"配置文件已存在：{CONFIG_FILE}")
    print(f"原始模板目录：{INPUT_TEMPLATE_DIR}")
    print(f"已分割模板目录：{TEMPLATE_DIR}")
    print(f"日志目录：{LOG_DIR}")
    return 0


def status_command() -> int:
    from wq_workflow.dashboard.cli_formatter import CLIStatusFormatter
    from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator

    snapshot = DashboardStatusAggregator().build_snapshot()
    print(CLIStatusFormatter().format_snapshot(snapshot, compact=True, limit=8))
    print("结束流程：人工关闭对应 CLI 窗口/进程；status 命令只读，不会清理或修改运行状态。")
    return 0


def print_banner() -> None:
    print("=" * 64)
    print("WorldQuant + DeepSeek 自动迭代工作流")
    print("边界：只做 Simulate 与 Add to Favorites，绝不执行 Submit。")
    print("=" * 64)


def print_help() -> None:
    print_banner()
    print("常用命令：")
    print("  python worldquant_auto_workflow.py")
    print("  python worldquant_auto_workflow.py split --template-file .\\input_templates\\test.txt")
    print("  python worldquant_auto_workflow.py run --use-split --max-templates 1")
    print("  python worldquant_auto_workflow.py status")


def write_pid_file() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid_file(*, force: bool = False) -> None:
    try:
        if PID_FILE.exists() and (force or PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid())):
            PID_FILE.unlink()
    except Exception:
        pass


def read_pid() -> int | None:
    try:
        text = PID_FILE.read_text(encoding="utf-8").strip()
        return int(text) if text else None
    except Exception:
        return None


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except Exception:
            return False
        output = decode_subprocess_output(result.stdout) + "\n" + decode_subprocess_output(result.stderr)
        return str(pid) in output
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def decode_subprocess_output(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    encodings = [
        "utf-8-sig",
        locale.getpreferredencoding(False),
        "mbcs" if os.name == "nt" else "",
        "gbk",
    ]
    for encoding in dict.fromkeys(item for item in encodings if item):
        try:
            return data.decode(encoding)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


def read_config_json() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return default_config()
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"config.json 不是合法 JSON：{exc}") from exc


def write_config_json(raw: dict[str, Any]) -> None:
    CONFIG_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_config() -> dict[str, Any]:
    return {
        "email": "",
        "password": "",
        "login_url": "https://platform.worldquantbrain.com/login",
        "headless": False,
        "slow_mo": 0,
        "browser_executable_path": "",
        "max_templates": 0,
        "max_iterations_per_template": 12,
        "simulation_wait_seconds": 900,
        "v2": {
            "enable_v2_engine": True,
            "enable_behavior_sc_pipeline": True,
            "rollout_phase": 6,
        },
        "evolution": {
            "enable_survival_memory": True,
            "enable_pending_reward": True,
            "enable_template_governance": True,
            "enable_exploration_pressure": True,
            "enable_adaptive_legacy": True,
        },
        "insight": {
            "enable_research_insights": True,
            "top_k": 5,
            "distill_interval": 50,
            "min_samples": 20,
            "max_prompt_clusters": 16,
        },
        "thresholds": {
            "sharpe_min": 1.25,
            "fitness_min": 1.0,
            "sub_universe_sharpe_min": -0.49,
            "turnover_min": 1.0,
            "turnover_max": 70.0,
        },
        "deepseek": {
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-pro",
            "temperature": 0.15,
            "max_tokens": 3000,
            "_max_tokens_comment": "Legacy field; runtime DeepSeek API calls always use the fixed maximum 384000.",
        },
        "_comment": "敏感信息可用环境变量 WORLDQUANT_EMAIL/WORLDQUANT_PASSWORD/DEEPSEEK_API_KEY 注入。",
    }
