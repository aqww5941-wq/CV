$ErrorActionPreference = "Stop"
$host.ui.RawUI.WindowTitle = "AI 智慧前台数字人系统"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI 智慧前台数字人系统 - 一键启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$avatarDir = Join-Path $root "avatar"
$avatarPort = 3456

# ── 1. 启动数据库服务 (WSL / 本地自适应) ──
Write-Host "[1/4] 启动数据库服务..." -ForegroundColor Yellow

$hasWsl = $false
try { $hasWsl = (wsl -l -q 2>$null | Out-String).Trim() -ne "" } catch {}

if ($hasWsl) {
    try {
        wsl -e bash -c "sudo service mysql start 2>/dev/null; sudo service redis-server start 2>/dev/null; sudo service postgresql start 2>/dev/null" 2>$null
        Write-Host "       MySQL + Redis + PostgreSQL (WSL) 已就绪" -ForegroundColor Green
    } catch {
        Write-Host "       WSL 服务启动失败, 请手动确认" -ForegroundColor DarkYellow
    }
} else {
    $svcNames = @("MySQL*", "postgresql*", "Redis*")
    foreach ($svcPattern in $svcNames) {
        $svc = Get-Service -Name $svcPattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($svc -and $svc.Status -ne "Running") {
            Write-Host "       启动 $($svc.Name)..." -ForegroundColor Gray
            Start-Service $svc.Name -ErrorAction SilentlyContinue
        }
    }
    Write-Host "       本地数据库服务已就绪" -ForegroundColor Green
}

# ── 2. 清除测试数据 (Redis 缓存 + 签到记录) ──
Write-Host "[2/5] 清除测试数据..." -ForegroundColor Yellow

try {
    if ($hasWsl) {
        wsl -e bash -c "redis-cli KEYS 'checkin:*' | xargs -r redis-cli DEL" 2>$null
        wsl -e bash -c "mysql -u root -p123456 attendance -e 'TRUNCATE TABLE attendance;' 2>/dev/null"
    } else {
        & redis-cli KEYS "checkin:*" | ForEach-Object { & redis-cli DEL $_ } 2>$null
    }
    Write-Host "       Redis 签到缓存 + MySQL 签到记录已清除" -ForegroundColor Green
} catch {
    Write-Host "       清除失败 (不影响启动)" -ForegroundColor DarkYellow
}

# ── 3. 启动 Node 数字人服务 ──
Write-Host "[3/5] 启动数字人前端 (端口 $avatarPort)..." -ForegroundColor Yellow

$existing = Get-NetTCPConnection -LocalPort $avatarPort -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "       端口 $avatarPort 被占用, 尝试释放..." -ForegroundColor DarkYellow
    Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

$nodeProcess = Start-Process -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $avatarDir -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

if ($nodeProcess.HasExited) {
    Write-Host "       Node 启动失败! 请检查 $avatarDir\server.js" -ForegroundColor Red
    exit 1
}
Write-Host "       数字人前端已启动 (PID: $($nodeProcess.Id))" -ForegroundColor Green

# ── 4. 启动 Python 人脸识别 ──
Write-Host "[4/5] 启动人脸识别引擎..." -ForegroundColor Yellow

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}

$pyProcess = Start-Process -FilePath $venvPython -ArgumentList "app.py" -WorkingDirectory $root -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 4

if ($pyProcess.HasExited) {
    Write-Host "       Python 启动失败! 请检查 $root\app.py" -ForegroundColor Red
    Write-Host "       尝试在终端手动运行: cd $root && python app.py" -ForegroundColor DarkYellow
    Stop-Process -Id $nodeProcess.Id -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "       人脸识别引擎已启动 (PID: $($pyProcess.Id))" -ForegroundColor Green

# ── 5. 打开浏览器 ──
Write-Host "[5/5] 打开数字人页面..." -ForegroundColor Yellow

$url = "http://localhost:$avatarPort/?display"
Start-Process "msedge" -ArgumentList "--new-window", "--kiosk", $url, "--edge-kiosk-type=fullscreen"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  系统运行中!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  数字人页面: $url" -ForegroundColor White
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
        if ($pyProcess.HasExited) {
            Write-Host "人脸识别引擎已退出" -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 3
    }
} finally {
    Write-Host "正在停止服务..." -ForegroundColor Yellow
    Stop-Process -Id $nodeProcess.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $pyProcess.Id -Force -ErrorAction SilentlyContinue
    Write-Host "已停止" -ForegroundColor Green
}