@echo off
rem Ladder snapshot for the Windows Task Scheduler; appends to results\track.log
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
python scout\track.py >> results\track_task.log 2>&1
