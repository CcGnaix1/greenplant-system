$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir = Join-Path $Root ".run"

foreach ($name in @("ai-win", "java-win")) {
    $pidFile = Join-Path $RunDir "$name.pid"
    if (Test-Path $pidFile) {
        $savedPid = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($savedPid) {
            & taskkill.exe /PID $savedPid /T /F 2>$null | Out-Null
            Write-Host "已停止 $name 服务。" -ForegroundColor Green
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "服务已停止。"
