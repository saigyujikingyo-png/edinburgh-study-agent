@echo off
setlocal
if not exist "%~dp0payload\runtime\Scripts\pythonw.exe" (
  echo Extract the complete UoE Companion Windows setup ZIP before running Install.cmd.
  pause
  exit /b 1
)
start "UoE Companion setup" "%~dp0payload\runtime\Scripts\pythonw.exe" -m edinburgh_study_agent.setup_ui --bundle "%~dp0payload"
