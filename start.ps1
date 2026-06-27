$ErrorActionPreference = "Stop"
$host.ui.RawUI.WindowTitle = "AI 智慧前台数字人系统"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI 智慧前台数字人系统 - 一键启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$avatarDir = Join-Path $root "avatar"
$avatarPort = 3456

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        Write-Host "       未找到 .env，使用系统环境变量和默认配置" -ForegroundColor DarkGray
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        if ($line -notmatch "^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$") {
            return
        }

        $name = $matches[1]
        $value = $matches[2].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }

    Write-Host "       已加载 .env 配置" -ForegroundColor Green
}

Import-DotEnv (Join-Path $root ".env")

function Read-YesNo {
    param(
        [string]$Prompt,
        [bool]$DefaultYes = $true
    )

    $suffix = if ($DefaultYes) { "Y/n" } else { "y/N" }
    while ($true) {
        $answer = Read-Host "$Prompt ($suffix)"
        if ([string]::IsNullOrWhiteSpace($answer)) {
            return $DefaultYes
        }
        switch ($answer.Trim().ToLowerInvariant()) {
            "y" { return $true }
            "yes" { return $true }
            "是" { return $true }
            "n" { return $false }
            "no" { return $false }
            "否" { return $false }
            default { Write-Host "       请输入 y 或 n" -ForegroundColor DarkYellow }
        }
    }
}

$logDir = Join-Path $root "cache\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$nodeLog = Join-Path $logDir "avatar-node.log"
$nodeErrLog = Join-Path $logDir "avatar-node.err.log"
$pythonLog = Join-Path $logDir "app-python.log"
$pythonErrLog = Join-Path $logDir "app-python.err.log"
$pyProcess = $null

# ── 1. 数据库服务确认 / WSL 启动 ──
Write-Host "[1/5] 数据库服务确认..." -ForegroundColor Yellow

$dbAlreadyRunning = Read-YesNo "MySQL / Redis / PostgreSQL 服务是否已经开启？"
$hasWsl = $false
$mysqlOk = $false
$redisOk = $false
$pgsqlOk = $false

if ($dbAlreadyRunning) {
    try { $hasWsl = (wsl -l -q 2>$null | Out-String).Trim() -ne "" } catch {}
    Write-Host "       已确认数据库服务开启，跳过 WSL 启动" -ForegroundColor Green
    $mysqlOk = $true
    $redisOk = $true
    $pgsqlOk = $true
}
else {
    try { $hasWsl = (wsl -l -q 2>$null | Out-String).Trim() -ne "" } catch {}
    if (-not $hasWsl) {
        Write-Host "       未检测到可用 WSL，无法自动启动数据库服务。" -ForegroundColor Red
        Write-Host "       请手动启动 MySQL / Redis / PostgreSQL 后重新运行脚本。" -ForegroundColor DarkYellow
        exit 1
    }

    Write-Host "       正在通过 WSL 启动数据库服务..." -ForegroundColor Gray

    wsl -e bash -c "sudo service mysql start 2>/dev/null" 2>$null
    Start-Sleep -Seconds 1
    wsl -e bash -c "sudo service mysql status 2>/dev/null" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "       MySQL      启动成功 (WSL)" -ForegroundColor Green
        $mysqlOk = $true
    }
    else {
        Write-Host "       MySQL      启动失败! 请检查 WSL 中 MySQL 是否安装" -ForegroundColor Red
    }

    wsl -e bash -c "sudo service redis-server start 2>/dev/null" 2>$null
    Start-Sleep -Seconds 1
    wsl -e bash -c "sudo service redis-server status 2>/dev/null" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "       Redis      启动成功 (WSL)" -ForegroundColor Green
        $redisOk = $true
    }
    else {
        Write-Host "       Redis      启动失败! 请检查 WSL 中 Redis 是否安装" -ForegroundColor Red
    }

    wsl -e bash -c "sudo service postgresql start 2>/dev/null" 2>$null
    Start-Sleep -Seconds 1
    wsl -e bash -c "sudo service postgresql status 2>/dev/null" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "       PostgreSQL 启动成功 (WSL)" -ForegroundColor Green
        $pgsqlOk = $true
    }
    else {
        Write-Host "       PostgreSQL 启动失败! 请检查 WSL 中 PostgreSQL 是否安装" -ForegroundColor Red
    }
}

if (-not $mysqlOk) {
    Write-Host "       MySQL 不可用，考勤模块无法初始化，启动已停止。" -ForegroundColor Red
    Write-Host "       请先启动 MySQL，或后续为 app.py 增加无数据库降级模式。" -ForegroundColor DarkYellow
    exit 1
}

# ── 2. 可选清除测试数据 (Redis 缓存 + 签到记录) ──
Write-Host "[2/5] 检查测试数据清理配置..." -ForegroundColor Yellow

if ($env:CLEAR_TEST_DATA -eq "1") {
    Write-Host "       CLEAR_TEST_DATA=1，正在清除测试数据..." -ForegroundColor Yellow

    if ($redisOk) {
        try {
            $redisPatterns = @("checkin:*", "checkin_cooldown:*", "checkout:*")
            if ($hasWsl) {
                foreach ($pattern in $redisPatterns) {
                    wsl -e bash -c "redis-cli KEYS '$pattern' | xargs -r redis-cli DEL" 2>$null
                }
            }
            else {
                foreach ($pattern in $redisPatterns) {
                    & redis-cli KEYS $pattern | ForEach-Object { & redis-cli DEL $_ } 2>$null
                }
            }
            Write-Host "       Redis 签到缓存已清除" -ForegroundColor Green
        }
        catch {
            Write-Host "       Redis 清除失败 (不影响启动)" -ForegroundColor DarkYellow
        }
    }
    else {
        Write-Host "       Redis 不可用, 跳过清除" -ForegroundColor DarkYellow
    }

    if ($mysqlOk) {
        try {
            if ($hasWsl) {
                wsl -e bash -c "mysql -u root -p123456 attendance -e 'TRUNCATE TABLE attendance;' 2>/dev/null"
            }
            Write-Host "       MySQL 签到记录已清除" -ForegroundColor Green
        }
        catch {
            Write-Host "       MySQL 清除失败 (不影响启动)" -ForegroundColor DarkYellow
        }
    }
    else {
        Write-Host "       MySQL 不可用, 跳过清除" -ForegroundColor DarkYellow
    }
}
else {
    Write-Host "       已跳过测试数据清理。如需演示清库，请在 .env 设置 CLEAR_TEST_DATA=1" -ForegroundColor Green
}

# ── 3. 启动 Node 数字人服务 ──
Write-Host "[3/5] 启动数字人前端 (端口 $avatarPort)..." -ForegroundColor Yellow

$existing = Get-NetTCPConnection -LocalPort $avatarPort -ErrorAction SilentlyContinue |
Where-Object { $_.OwningProcess -and $_.OwningProcess -gt 0 } |
Select-Object -ExpandProperty OwningProcess -Unique
if ($existing) {
    Write-Host "       端口 $avatarPort 被占用, 尝试释放..." -ForegroundColor DarkYellow
    $existing | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

$nodeProcess = Start-Process -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $avatarDir -PassThru -WindowStyle Hidden -RedirectStandardOutput $nodeLog -RedirectStandardError $nodeErrLog
Start-Sleep -Seconds 2

if ($nodeProcess.HasExited) {
    Write-Host "       Node 启动失败! 请检查 $avatarDir\server.js" -ForegroundColor Red
    exit 1
}
Write-Host "       数字人前端已启动 (PID: $($nodeProcess.Id))" -ForegroundColor Green

if ($env:ENABLE_TTS_PREWARM -eq "1") {
    Write-Host "       正在预生成数字人语音缓存..." -ForegroundColor Yellow
    $prewarmDeadline = (Get-Date).AddMinutes(5)
    $prewarmReady = $false
    while ((Get-Date) -lt $prewarmDeadline) {
        try {
            $status = Invoke-RestMethod -Uri "http://localhost:$avatarPort/tts-prewarm-status" -TimeoutSec 3
            $done = [int]$status.generated + [int]$status.skipped
            Write-Host ("       语音缓存: {0}/{1}" -f $done, $status.total) -ForegroundColor DarkGray
            if ($status.complete) {
                if ($status.error) {
                    Write-Host "       语音预生成失败: $($status.error)" -ForegroundColor Red
                    Stop-Process -Id $nodeProcess.Id -Force -ErrorAction SilentlyContinue
                    exit 1
                }
                else {
                    Write-Host "       语音缓存已就绪" -ForegroundColor Green
                    $prewarmReady = $true
                }
                break
            }
        }
        catch {
            Write-Host "       等待数字人服务响应..." -ForegroundColor DarkGray
        }
        Start-Sleep -Seconds 3
    }

    if (-not $prewarmReady) {
        Write-Host "       语音预生成未完成，系统不会继续启动。请检查网络或 Edge TTS 服务后重试。" -ForegroundColor Red
        Stop-Process -Id $nodeProcess.Id -Force -ErrorAction SilentlyContinue
        exit 1
    }
}
else {
    Write-Host "       已跳过旧版全量语音预生成，语音将按事件异步生成并缓存" -ForegroundColor Green
}

# ── 4. 打开浏览器并等待数字人加载 ──
Write-Host "[4/5] 打开数字人页面并等待模型加载..." -ForegroundColor Yellow

$url = "http://localhost:$avatarPort/?display&v=$([DateTimeOffset]::Now.ToUnixTimeSeconds())"
Start-Process "msedge" -ArgumentList "--new-window", "--kiosk", $url, "--edge-kiosk-type=fullscreen", "--autoplay-policy=no-user-gesture-required"

$avatarReadyDeadline = (Get-Date).AddMinutes(2)
$avatarReady = $false
while ((Get-Date) -lt $avatarReadyDeadline) {
    try {
        $ready = Invoke-RestMethod -Uri "http://localhost:$avatarPort/avatar-ready" -TimeoutSec 2
        if ($ready.ready) {
            Write-Host "       数字人模型已加载: $($ready.model)" -ForegroundColor Green
            $avatarReady = $true
            break
        }
        Write-Host "       等待数字人模型加载..." -ForegroundColor DarkGray
    }
    catch {
        Write-Host "       等待数字人页面响应..." -ForegroundColor DarkGray
    }
    Start-Sleep -Seconds 2
}

if (-not $avatarReady) {
    Write-Host "       数字人模型未加载完成，系统不会打开摄像头。" -ForegroundColor Red
    Stop-Process -Id $nodeProcess.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

# ── 5. 启动 Python 人脸识别 ──
Write-Host "[5/5] 启动人脸识别引擎..." -ForegroundColor Yellow

$oldAppProcesses = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match '(^| )app\.py( |$)' }
if ($oldAppProcesses) {
    Write-Host "       发现旧识别进程，正在清理..." -ForegroundColor DarkYellow
    $oldAppProcesses | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}

$pyProcess = Start-Process -FilePath $venvPython -ArgumentList "app.py" -WorkingDirectory $root -PassThru -WindowStyle Hidden -RedirectStandardOutput $pythonLog -RedirectStandardError $pythonErrLog
Start-Sleep -Seconds 4

if ($pyProcess.HasExited) {
    Write-Host "       Python 启动失败! 请检查 $root\app.py" -ForegroundColor Red
    Write-Host "       尝试在终端手动运行: cd $root && python app.py" -ForegroundColor DarkYellow
    Stop-Process -Id $nodeProcess.Id -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "       人脸识别引擎已启动 (PID: $($pyProcess.Id))" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  系统运行中!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  数字人页面: $url" -ForegroundColor White
Write-Host "  运行日志:   $logDir" -ForegroundColor DarkGray
Write-Host "  退出全屏:   按 F11" -ForegroundColor DarkGray
Write-Host "  关闭浏览器:  Alt+F4" -ForegroundColor DarkGray
Write-Host "  停止系统:    关闭此窗口" -ForegroundColor DarkGray
Write-Host ""

try {
    while ($true) {
        if ($nodeProcess.HasExited) {
            Write-Host "数字人前端已退出" -ForegroundColor Red
            break
        }
        if ($pyProcess -and $pyProcess.HasExited) {
            Write-Host "人脸识别引擎已退出" -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 3
    }
}
finally {
    Write-Host "正在停止服务..." -ForegroundColor Yellow
    Stop-Process -Id $nodeProcess.Id -Force -ErrorAction SilentlyContinue
    if ($pyProcess) {
        Stop-Process -Id $pyProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "已停止" -ForegroundColor Green
}
