$ErrorActionPreference = "Stop"
$root = "d:\CV"
$venv = "$root\.venv"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  重建 Python 虚拟环境" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. 删除旧环境
if (Test-Path $venv) {
    Write-Host "[1/3] 删除旧环境..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venv
    Write-Host "      已删除" -ForegroundColor Green
} else {
    Write-Host "[1/3] 无旧环境, 跳过" -ForegroundColor DarkGray
}

# 2. 创建新环境
Write-Host "[2/3] 创建虚拟环境..." -ForegroundColor Yellow
python -m venv $venv
Write-Host "      已创建" -ForegroundColor Green

# 3. 安装依赖
Write-Host "[3/3] 安装依赖..." -ForegroundColor Yellow
& "$venv\Scripts\pip.exe" install -r "$root\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
Write-Host "      安装完成" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  环境重建完成!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan