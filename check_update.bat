@echo off
python "%LOCALAPPDATA%\CornGetFromGit\check_updates.py" --single
if errorlevel 1 (
    echo Failed to update
    exit /b 1
) else (
    echo Update successful
    exit /b 0
) 