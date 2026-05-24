@echo off
setlocal
cd /d "%~dp0"

echo [DRY RUN] Checking files that would be removed...
python tools\clean_release.py

echo.
echo To actually clean release artifacts, run:
echo python tools\clean_release.py --apply

endlocal
