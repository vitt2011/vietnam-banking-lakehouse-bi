# ===============================================================================
# SCRIPT CAI DAT WINDOWS TASK SCHEDULER TU DONG CHAY HANG NGAY LUC 15:45
# Cấu hình chuẩn Enterprise: Tự chạy bù khi bật máy (StartWhenAvailable)
# Cho phép chạy khi dùng pin (DisallowStartIfOnBatteries = False)
# ===============================================================================

$TaskName = "StockAnalysis_DailyUpdate"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectDir = (Resolve-Path "$ScriptDir\..").Path
$BatPath = "$ScriptDir\02_run_daily_update.bat"

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "   CAI DAT TIEN TRINH TU DONG CAO DU LIEU CHUNG KHOAN (TASK SCHEDULER)" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "Ten tac vu      : $TaskName"
Write-Host "Thu muc du an   : $ProjectDir"
Write-Host "File thuc thi   : $BatPath"
Write-Host "Lich trinh      : Moi ngay tu Thu 2 den Thu 6 vao luc 15:45 (sau gio ATC)" -ForegroundColor Yellow
Write-Host "Co che chay bu  : Tu dong chay bu ngay khi mo may neu bo lo luc 15:45" -ForegroundColor Yellow

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatPath`" --no-pause" -WorkingDirectory "$ProjectDir"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 15:45
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force

if ($?) {
    Write-Host "`n[V] DA CAI DAT TU DONG HOA THANH CONG VAO WINDOWS TASK SCHEDULER!" -ForegroundColor Green
    Write-Host "-> Tu nay, cu moi 15:45 chieu ngay thuong, he thong se tu dong thuc day cao du lieu." -ForegroundColor Green
    Write-Host "-> Neu may tinh tat hoac ngu luc 15:45, he thong se TU DONG CHAY BU ngay khi mo may." -ForegroundColor Green
} else {
    Write-Host "`n[!] CO LOI TRONG QUA TRINH TAO TAC VU." -ForegroundColor Red
}

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "Nhan Enter de thoat..."
Read-Host
