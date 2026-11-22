@echo off
setlocal EnableDelayedExpansion
title VIETNAM BANKING LAKEHOUSE BI - LOCAL STREAMLIT DASHBOARD

echo ======================================================================
echo    VIETNAM BANKING LAKEHOUSE ^& BI PLATFORM
echo    KHOI DONG GIAO DIEN WEB DASHBOARD (LOCAL / SNAPSHOT MODE)
echo ======================================================================
echo.

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI
cd /d "%PROJECT_ROOT%"

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
) else if exist "%PROJECT_ROOT%\..\Stock_Analysis\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\..\Stock_Analysis\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [*] Python: %PYTHON_EXE%
set "PYTHONPATH=%PROJECT_ROOT%;%PROJECT_ROOT%\apps;%PROJECT_ROOT%\src;%PYTHONPATH%"
if not defined DATA_SOURCE_MODE set "DATA_SOURCE_MODE=snapshot"

REM Tu dong giai phong cong 8501 neu co tien trinh cu dang chay ngam
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8501 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

echo [*] Dang khoi dong Web Server Streamlit tai: http://localhost:8501
echo [*] Trinh duyet se tu dong mo len trong giay lat...
echo.

"%PYTHON_EXE%" -m streamlit run streamlit_app.py --server.port 8501 --browser.serverAddress localhost --server.headless false

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ======================================================================
    echo    [LOI] DASHBOARD BI DUNG HOAC KHOI DONG THAT BAI VOI MA: %ERRORLEVEL%
    echo ======================================================================
    pause
    exit /b %ERRORLEVEL%
)

endlocal
