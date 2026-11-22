@echo off
setlocal EnableDelayedExpansion
title VIETNAM BANKING DATA PLATFORM - LOCAL STREAMLIT DASHBOARD

echo ======================================================================
echo    NEN TANG DU LIEU 27 NGAN HANG VIET NAM (STOCK_ANALYSIS)
echo    KHOI DONG GIAO DIEN WEB DASHBOARD PHAN TICH CHUYEN SAU
echo ======================================================================
echo.

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
cd /d "%PROJECT_ROOT%"
set PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Khong tim thay Python trong moi truong ao tai: %PYTHON_EXE%
    echo Vui long kiem tra lai thu muc .venv!
    pause
    exit /b 1
)

set PYTHONPATH=%PROJECT_ROOT%;%PROJECT_ROOT%\apps;%PROJECT_ROOT%\src;%PROJECT_ROOT%\apps\dashboard;%PYTHONPATH%

REM Tu dong giai phong cong 8501 neu co tien trinh cu dang chay ngam
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8501 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

echo [*] Dang khoi dong Web Server Streamlit tai dia chi: http://localhost:8501
echo [*] Trinh duyet se tu dong mo len trong giay lat...
echo.

"%PYTHON_EXE%" -m streamlit run apps\dashboard\app.py --server.port 8501 --browser.serverAddress localhost --server.headless false

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ======================================================================
    echo    [LOI] DASHBOARD BI DUNG HOAC KHOI DONG THAT BAI VOI MA: %ERRORLEVEL%
    echo ======================================================================
    pause
    exit /b %ERRORLEVEL%
)

endlocal
