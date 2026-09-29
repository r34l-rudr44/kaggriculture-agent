@echo off
rem Scouting refresh for the Windows Task Scheduler: new losses, top-10 games, fingerprints, win model
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
echo ==== %date% %time% >> results\scout_task.log
python scout\scout.py losses >> results\scout_task.log 2>&1
python scout\scout.py top 6 >> results\scout_task.log 2>&1
python scout\fingerprint.py 3 >> results\scout_task.log 2>&1
python scout\learn.py > results\learn_latest.txt 2>&1
