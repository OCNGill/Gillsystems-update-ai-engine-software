@echo off
:: ============================================================
:: Gillsystems AI Stack Updater — Windows Launcher
:: update-ai-stack.bat
::
:: Elevates to Administrator, then invokes the Python agent.
:: All CLI arguments are forwarded to main.py.
:: ============================================================

:: Check for Administrator rights
NET SESSION >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [GASU] Requesting Administrator privileges...
    powershell -NoProfile -Command ^
        "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

:: Change to the directory containing this script
cd /d "%~dp0"

:: Verify Python 3.11+ is available
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [GASU] ERROR: Python not found on PATH.
    echo  Please install Python 3.11+ and ensure it is on your PATH.
    echo.
    pause
    exit /b 1
)

:: Check for Python 3.11+
python -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [GASU] ERROR: Python 3.11 or higher is required.
    python --version
    echo.
    pause
    exit /b 1
)

:: Install dependencies if requirements.txt is newer than last install marker
IF NOT EXIST ".deps_installed" (
    echo  [GASU] Installing Python dependencies...
    python -m pip install --quiet -r requirements.txt
    IF %ERRORLEVEL% NEQ 0 (
        echo  [GASU] ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    echo installed > .deps_installed
)

:: Run the agent
echo.
python -m src.main %*
SET EXIT_CODE=%ERRORLEVEL%

IF %EXIT_CODE% NEQ 0 (
    IF %EXIT_CODE% NEQ 130 (
        echo.
        echo  [GASU] Exited with code %EXIT_CODE%.
        pause
    )
)

exit /b %EXIT_CODE%
