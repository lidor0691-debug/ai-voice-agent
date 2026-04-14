@echo off
echo Registering Maya Dev Agent with Windows Task Scheduler...

schtasks /create /tn "MayaDevAgent" /tr "C:\Users\lidor\maya-ai\agent\run_daemon.bat" /sc onstart /ru "%USERNAME%" /rl HIGHEST /f

echo Done. The agent will now start automatically on boot.
echo To start it now without rebooting, run:
echo   schtasks /run /tn "MayaDevAgent"
pause
