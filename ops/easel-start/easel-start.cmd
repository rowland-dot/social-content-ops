@echo off
rem Double-click to bring Easel up: runs easel-start.sh in WSL and shows its one-line verdict.
wsl.exe -d Ubuntu --cd "%~dp0..\.." -- bash ops/easel-start/easel-start.sh
echo.
pause
