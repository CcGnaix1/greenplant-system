$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root ".logs"
$RunDir = Join-Path $Root ".run"
$AiRoot = Join-Path $Root "Plant-AI"
$MiniRoot = Join-Path $Root "zhinengPlant"
$JavaRoot = Join-Path $MiniRoot "backend-java"
$VenvRoot = Join-Path $AiRoot ".venv-win"

New-Item -ItemType Directory -Force -Path $LogDir, $RunDir | Out-Null

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path $Path)) {
        Copy-Item (Join-Path $Root ".env.example") $Path
        throw "已自动创建 .env。请先填写 MySQL、微信 AppID 和 AppSecret，然后重新双击 start-all.bat。"
    }
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
        }
    }
}

function Test-Placeholder([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    return [string]::IsNullOrWhiteSpace($value) -or $value.Contains("请填写")
}

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) { return @("py", "-3") }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
    throw "未找到 Python。请安装 Python 3.9 或更高版本，并勾选 Add Python to PATH。"
}

function Is-Running([string]$PidFile) {
    if (-not (Test-Path $PidFile)) { return $false }
    $savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if (-not $savedPid) { return $false }
    return $null -ne (Get-Process -Id $savedPid -ErrorAction SilentlyContinue)
}

Import-DotEnv (Join-Path $Root ".env")
if (Test-Placeholder "MYSQL_PASSWORD") { throw ".env 中的 MYSQL_PASSWORD 尚未填写。" }

if (-not (Get-Command mvn -ErrorAction SilentlyContinue)) {
    throw "未找到 Maven。请安装 Maven，并把 mvn 加入系统 PATH。"
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw "未找到 Java。请安装 JDK 17 或更高版本，并配置 JAVA_HOME。"
}

$python = @(Find-Python)
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "首次运行：正在创建 Windows Python 环境……" -ForegroundColor Cyan
    if ($python.Count -eq 2) { & $python[0] $python[1] -m venv $VenvRoot }
    else { & $python[0] -m venv $VenvRoot }
}

$dependencyCheck = & $VenvPython -c "import fastapi, uvicorn, onnxruntime, albumentations" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "首次运行：正在安装 AI 依赖，可能需要几分钟……" -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $AiRoot "service\requirements.txt")
}

$env:PLANT_UPLOAD_ROOT = Join-Path $JavaRoot "uploads"
$env:NO_ALBUMENTATIONS_UPDATE = "1"

$AiPidFile = Join-Path $RunDir "ai-win.pid"
if (Is-Running $AiPidFile) {
    Write-Host "AI 服务已经运行。" -ForegroundColor Yellow
} else {
    $aiLog = Join-Path $LogDir "ai-win.log"
    $aiArgs = "/c `"cd /d `"$AiRoot\service`" && `"$VenvPython`" -m uvicorn main:app --host 127.0.0.1 --port 5001 > `"$aiLog`" 2>&1`""
    $aiProcess = Start-Process cmd.exe -ArgumentList $aiArgs -WindowStyle Hidden -PassThru
    Set-Content -Path $AiPidFile -Value $aiProcess.Id
    Write-Host "AI 服务正在启动：http://127.0.0.1:5001" -ForegroundColor Green
}

$JavaPidFile = Join-Path $RunDir "java-win.pid"
if (Is-Running $JavaPidFile) {
    Write-Host "Java 服务已经运行。" -ForegroundColor Yellow
} else {
    $javaLog = Join-Path $LogDir "java-win.log"
    $javaArgs = "/c `"cd /d `"$JavaRoot`" && mvn spring-boot:run > `"$javaLog`" 2>&1`""
    $javaProcess = Start-Process cmd.exe -ArgumentList $javaArgs -WindowStyle Hidden -PassThru
    Set-Content -Path $JavaPidFile -Value $javaProcess.Id
    Write-Host "Java 服务正在启动：http://127.0.0.1:8081/api" -ForegroundColor Green
}

Write-Host ""
Write-Host "启动命令已执行。日志目录：$LogDir" -ForegroundColor Cyan
Write-Host "如果小程序真机无法连接，请修改 zhinengPlant\app.js 顶部的 BACKEND_BASE_URL。"
Write-Host "按任意键关闭此窗口，服务会继续在后台运行。"
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
