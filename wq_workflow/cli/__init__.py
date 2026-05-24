from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow.paths import ROOT, ensure_runtime_files
from wq_workflow import cli_legacy as _legacy
from .main import main

print_banner = _legacy.print_banner
workflow_menu = _legacy.workflow_menu
split_menu = _legacy.split_menu
status_command = _legacy.status_command
init_command = _legacy.init_command
run_command = _legacy.run_command
split_command = _legacy.split_command
print_help = _legacy.print_help
resolve_project_path = _legacy.resolve_project_path
format_bytes = _legacy.format_bytes


def menu_command() -> int:
    ensure_runtime_files()
    print_banner()
    while True:
        try:
            print()
            print("???")
            print("  1. ?????")
            print("  2. ????")
            print("  3. ????/API Key")
            print("  4. ?????")
            print("  5. ????")
            print("  6. ????")
            print("  0. ??")
            choice = input("????").strip()
            if choice == "1":
                workflow_menu()
            elif choice == "2":
                split_menu()
            elif choice == "3":
                _legacy.ensure_config_ready(force_prompt=True)
            elif choice == "4":
                status_command()
            elif choice == "5":
                log_export_menu()
            elif choice == "6":
                log_import_menu()
            elif choice == "0":
                print("????")
                return 0
            else:
                print("??? 0-6?")
        except KeyboardInterrupt:
            print("\n????????CLI ??????")
        except Exception as exc:
            print(f"?????{exc}")


def log_export_menu() -> int:
    ensure_runtime_files()
    print()
    print("????")
    output_dir = resolve_project_path(input("??????? log_exports??").strip() or "log_exports")
    archive_choice = input("?????1=zip?????2=tar.gz?3=????").strip()
    archive_format = {"1": "zip", "2": "tar.gz", "3": ""}.get(archive_choice or "1", "zip")
    alpha_id = input("? alpha_id ??????????").strip() or None
    since = input("???? since???????").strip() or None
    until = input("???? until???????").strip() or None
    task_id = input("? task_id ??????????").strip() or None
    worker_id = input("? worker_id ??????????").strip() or None
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
        print(f"???????{exc}")
        return 1
    print("???????")
    print(f"Export ID?{result.export_id}")
    print(f"?????{result.export_dir}")
    print(f"Manifest?{result.manifest_path}")
    print(f"????{result.files_count}")
    print(f"????{format_bytes(result.total_bytes)}")
    if getattr(result, "archive_paths", None):
        print("?????")
        for path in result.archive_paths:
            print(f"  {path}")
    else:
        print("????????")
    for warning in getattr(result, "warnings", []) or []:
        print(f"  - {warning}")
    return 0


def log_import_menu() -> int:
    ensure_runtime_files()
    print()
    print("????")
    source_text = input("??? export ??? zip/tar.gz/part001 ???").strip().strip('"')
    if not source_text:
        print("????????")
        return 1
    source = resolve_project_path(source_text)
    mode_choice = input("?????1=offline?????2=replay?3=incremental?4=restore?").strip()
    mode = {"1": "offline", "2": "replay", "3": "incremental", "4": "restore"}.get(mode_choice or "1", "offline")
    if mode == "restore":
        confirm = input("restore ???????????? RESTORE ???").strip()
        if confirm != "RESTORE":
            print("??? restore ???")
            return 0
    try:
        from log_manager import import_logs

        result = import_logs(source, ROOT, mode=mode, resume=True, conflict_policy="keep_existing")
    except Exception as exc:
        print(f"???????{exc}")
        return 1
    print("???????")
    print(f"???{result.mode}")
    print(f"?????{result.target_dir}")
    print(f"??????{len(result.imported_files)}")
    print(f"??????{len(result.skipped_files)}")
    for warning in getattr(result, "warnings", []) or []:
        print(f"  - {warning}")
    for error in getattr(result, "errors", []) or []:
        print(f"  - {error}")
    return 0


__all__ = [
    "main",
    "menu_command",
    "log_export_menu",
    "log_import_menu",
    "ensure_runtime_files",
    "print_banner",
    "ROOT",
]
