Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  数字人 Epsilon 启动器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. 显示屏模式 (纯净全屏, 用于大屏展示)" -ForegroundColor White
Write-Host "  2. 开发模式   (带表情/动作调试面板)" -ForegroundColor White
Write-Host ""
$choice = Read-Host "请选择 [1/2]"

$port = 3456
$url = "http://localhost:$port/"

$isKiosk = $false
if ($choice -eq "1") {
    $url += "?display"
    $isKiosk = $true
} elseif ($choice -eq "2") {
    # 普通模式, 不加参数
} else {
    Write-Host "无效选择, 默认开发模式" -ForegroundColor Yellow
}

# 杀掉旧进程
$oldPid = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
if ($oldPid) {
    Write-Host "发现端口 $port 被占用 (PID: $oldPid), 正在关闭..." -ForegroundColor Yellow
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Write-Host "启动 Node 服务..." -ForegroundColor Green
$nodeJob = Start-Process -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $PSScriptRoot -PassThru

Start-Sleep -Seconds 2

if ($isKiosk) {
    Write-Host "全屏启动 Edge..." -ForegroundColor Green
    Start-Process "msedge" -ArgumentList "--kiosk", $url, "--no-first-run", "--no-default-browser-check", "--edge-kiosk-type=fullscreen"
    Write-Host ""
    Write-Host "显示屏模式已启动" -ForegroundColor Yellow
    Write-Host "  退出全屏: F11 | 关闭: Alt+F4" -ForegroundColor Gray
} else {
    Write-Host "打开浏览器..." -ForegroundColor Green
    Start-Process $url
    Write-Host ""
    Write-Host "开发模式已启动" -ForegroundColor Yellow
    Write-Host "  右侧面板: 表情/动作调试" -ForegroundColor Gray
}

Write-Host "  停止服务: 关闭此窗口" -ForegroundColor Gray