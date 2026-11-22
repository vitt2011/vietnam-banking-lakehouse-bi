@echo off
chcp 65001 > nul
title [Stock_Analysis] Tien Trinh Cap Nhat Du Lieu Tu Dong Hang Ngay

echo ===============================================================================
echo     TIEN TRINH TU DONG DONG BO GIA TANG DU LIEU HANG NGAY (DAILY UPDATE)
echo ===============================================================================
echo Thoi gian khoi chay: %date% %time%

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
cd /d "%PROJECT_DIR%"

if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
    set PYTHON_EXE="%PROJECT_DIR%\.venv\Scripts\python.exe"
) else (
    set PYTHON_EXE=python
)

echo Dang su dung Python: %PYTHON_EXE%
echo.

%PYTHON_EXE% "%SCRIPT_DIR%03_run_pipeline.py" --mode daily

if %ERRORLEVEL% equ 0 (
    echo.
    echo [OK] TIEN TRINH CAP NHAT DU LIEU HOAN TAT XUAT SAC!
) else (
    echo.
    echo [!] CO LOI TRONG QUA TRINH THUC THI. VUI LONG KIEM TRA LOG TAI:
    echo     runtime\logs\pipeline\ (kiem tra file daily moi nhat)
)

echo ===============================================================================
if not "%1"=="--no-pause" pause

