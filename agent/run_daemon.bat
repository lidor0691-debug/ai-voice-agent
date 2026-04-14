@echo off
cd /d C:\Users\lidor\maya-ai
call venv\Scripts\activate.bat
python -m agent.daemon >> agent\daemon.log 2>&1
