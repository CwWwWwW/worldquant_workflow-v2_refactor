@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
python worldquant_auto_workflow.py %*
echo.
echo CLI 已返回。窗口不会自动关闭；请人工关闭当前窗口结束进程链。
pause >nul
