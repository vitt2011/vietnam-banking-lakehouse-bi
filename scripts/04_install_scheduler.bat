@echo off
chcp 65001 > nul
title Cai dat Windows Task Scheduler Tu Dong

echo ===============================================================================
echo   CAI DAT TIEN TRINH TU DONG CAO DU LIEU CHUNG KHOAN (WINDOWS TASK SCHEDULER)
echo ===============================================================================

set SCRIPT_DIR=%~dp0
set BAT_PATH=%SCRIPT_DIR%02_run_daily_update.bat

echo Ten tac vu   : StockAnalysis_DailyUpdate
echo File thuc thi: %BAT_PATH%
echo Lich trinh   : Moi ngay Thu 2 den Thu 6 vao luc 15:45 chieu
echo.

schtasks /create /tn "StockAnalysis_DailyUpdate" /tr "cmd.exe /c \"%BAT_PATH%\" --no-pause" /sc weekly /d MON,TUE,WED,THU,FRI /st 15:45 /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo ===============================================================================
    echo [V] DA CAI DAT TU DONG HOA THANH CONG!
    echo Cu moi 15:45 chieu ngay thuong, he thong se tu dong thuc day cap nhat du lieu.
    echo ===============================================================================
) else (
    echo.
    echo [!] CO LOI KHI TAO TASK SCHEDULER.
)

echo.
pause

