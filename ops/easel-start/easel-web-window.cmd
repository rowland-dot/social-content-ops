@echo off
rem Runs the Easel web workspace in a window that stays open. easel-start.sh opens this file through
rem explorer.exe, because a window started straight from Claude's shell call is closed when the call ends.
rem bash -i so nvm loads Node; "exec bash" keeps the window open, with EASEL-EXITED above it, if the server stops.
title Easel web workspace (localhost:7860)
wsl.exe -d Ubuntu --cd "%~dp0..\.." -- bash -ic ".venv/bin/easel web --port 7860; echo EASEL-EXITED; exec bash"
