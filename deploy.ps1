$ErrorActionPreference = "Stop"
$host.ui.RawUI.WindowTitle = "CV 数字人系统 - 部署"

Write-Host @"
========================================
  CV 智慧前台数字人系统 - 一键部署
========================================
"@ -ForegroundColor Cyan

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCmd = "python"
$nodeCmd = "node"

# ════════════════════════════════════════
# 1. 环境检查
# ════════════════════════════════════════
Write-Host "`n[1/6] 环境检查..." -ForegroundColor Yellow

try {
    $pyVer = & $pythonCmd --version 2>&1
    Write-Host "       Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "       未找到 Python, 请先安装 Python 3.10+ https://python.org" -ForegroundColor Red
    exit 1
}

try {
    $nodeVer = & $nodeCmd --version 2>&1
    Write-Host "       Node.js: $nodeVer" -ForegroundColor Green
} catch {
    Write-Host "       未找到 Node.js, 请先安装 https://nodejs.org" -ForegroundColor Red
    exit 1
}

# ════════════════════════════════════════
# 2. 数据库准备 (WSL / 本地自适应)
# ════════════════════════════════════════
Write-Host "`n[2/6] 数据库准备..." -ForegroundColor Yellow

$hasWsl = $false
try { $hasWsl = (wsl -l -q 2>$null | Out-String).Trim() -ne "" } catch {}

$useWsl = $false
$mysqlCmd = $null
$psqlCmd = $null

if ($hasWsl) {
    Write-Host "       检测到 WSL, 使用 WSL 数据库..." -ForegroundColor Cyan
    $useWsl = $true
    wsl -e bash -c "
        sudo service mysql start 2>/dev/null || echo 'MySQL 已运行'
        sudo service redis-server start 2>/dev/null || echo 'Redis 已运行'
        sudo service postgresql start 2>/dev/null || echo 'PostgreSQL 已运行'
    "
    Write-Host "       MySQL / Redis / PostgreSQL 已启动" -ForegroundColor Green
} else {
    Write-Host "       无 WSL, 检测本地数据库..." -ForegroundColor Cyan

    # 检测 MySQL (Windows 服务)
    $mysqlService = Get-Service -Name "MySQL*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($mysqlService) {
        if ($mysqlService.Status -ne "Running") {
            Write-Host "       启动 MySQL 服务..." -ForegroundColor Gray
            Start-Service $mysqlService.Name
        }
        # 找 mysql.exe
        $mysqlPaths = @(
            "${env:ProgramFiles}\MySQL\MySQL Server 9.1\bin\mysql.exe",
            "${env:ProgramFiles}\MySQL\MySQL Server 9.0\bin\mysql.exe",
            "${env:ProgramFiles}\MySQL\MySQL Server 8.4\bin\mysql.exe",
            "${env:ProgramFiles}\MySQL\MySQL Server 8.0\bin\mysql.exe",
            "${env:ProgramFiles(x86)}\MySQL\MySQL Server 8.0\bin\mysql.exe"
        )
        foreach ($p in $mysqlPaths) { if (Test-Path $p) { $mysqlCmd = $p; break } }
        if ($mysqlCmd) { Write-Host "       MySQL 已就绪 ($($mysqlService.Name))" -ForegroundColor Green }
        else { Write-Host "       MySQL 服务已运行, 但未找到 mysql.exe" -ForegroundColor DarkYellow }
    } else {
        Write-Host "       MySQL 服务未找到!" -ForegroundColor Red
        Write-Host "       请安装 MySQL: https://dev.mysql.com/downloads/installer/" -ForegroundColor Yellow
        Write-Host "       安装后设置 root 密码为 123456" -ForegroundColor Yellow
    }

    # 检测 PostgreSQL (Windows 服务)
    $pgService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pgService) {
        if ($pgService.Status -ne "Running") {
            Write-Host "       启动 PostgreSQL 服务..." -ForegroundColor Gray
            Start-Service $pgService.Name
        }
        $pgPaths = @(
            "${env:ProgramFiles}\PostgreSQL\17\bin\psql.exe",
            "${env:ProgramFiles}\PostgreSQL\16\bin\psql.exe",
            "${env:ProgramFiles}\PostgreSQL\15\bin\psql.exe",
            "${env:ProgramFiles}\PostgreSQL\14\bin\psql.exe"
        )
        foreach ($p in $pgPaths) { if (Test-Path $p) { $psqlCmd = $p; break } }
        if ($psqlCmd) { Write-Host "       PostgreSQL 已就绪 ($($pgService.Name))" -ForegroundColor Green }
        else { Write-Host "       PostgreSQL 服务已运行, 但未找到 psql.exe" -ForegroundColor DarkYellow }
    } else {
        Write-Host "       PostgreSQL 服务未找到!" -ForegroundColor Red
        Write-Host "       请安装 PostgreSQL: https://www.postgresql.org/download/windows/" -ForegroundColor Yellow
        Write-Host "       安装后设置 postgres 密码为 123456, 端口 5434" -ForegroundColor Yellow
    }

    # 检测 Redis (Windows 服务 或 端口)
    $redisService = Get-Service -Name "Redis*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($redisService) {
        if ($redisService.Status -ne "Running") {
            Write-Host "       启动 Redis 服务..." -ForegroundColor Gray
            Start-Service $redisService.Name
        }
        Write-Host "       Redis 已就绪 ($($redisService.Name))" -ForegroundColor Green
    } else {
        $redisPort = Get-NetTCPConnection -LocalPort 6379 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($redisPort) {
            Write-Host "       Redis 已在运行 (端口 6379)" -ForegroundColor Green
        } else {
            Write-Host "       Redis 未运行!" -ForegroundColor Red
            Write-Host "       请安装 Redis for Windows: https://github.com/tporadowski/redis/releases" -ForegroundColor Yellow
            Write-Host "       下载 .msi 安装后自动注册为 Windows 服务" -ForegroundColor Yellow
        }
    }

    if (-not $mysqlCmd -or -not $psqlCmd) {
        Write-Host ""
        Write-Host "       数据库配置参考:" -ForegroundColor DarkGray
        Write-Host "       MySQL:  root / 123456 / attendance (端口 3306)" -ForegroundColor DarkGray
        Write-Host "       PostgreSQL: postgres / 123456 / face_db (端口 5434)" -ForegroundColor DarkGray
        Write-Host "       Redis: 无密码 / 端口 6379" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "       请确保上述数据库已安装并运行, 然后重新运行此脚本" -ForegroundColor Yellow
        exit 1
    }
}

# ════════════════════════════════════════
# 3. Python 虚拟环境
# ════════════════════════════════════════
Write-Host "`n[3/6] Python 环境..." -ForegroundColor Yellow

$venv = Join-Path $root ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "       创建虚拟环境..." -ForegroundColor Gray
    & $pythonCmd -m venv $venv
}
$pip = Join-Path $venv "Scripts\pip.exe"
Write-Host "       安装依赖..." -ForegroundColor Gray
& $pip install -r (Join-Path $root "requirements.txt") -i https://pypi.tuna.tsinghua.edu.cn/simple
Write-Host "       Python 依赖安装完成" -ForegroundColor Green

# ════════════════════════════════════════
# 4. Node.js 依赖
# ════════════════════════════════════════
Write-Host "`n[4/6] Node.js 环境..." -ForegroundColor Yellow

$avatarDir = Join-Path $root "avatar"
if (-not (Test-Path (Join-Path $avatarDir "node_modules"))) {
    Push-Location $avatarDir
    npm install --registry=https://registry.npmmirror.com
    Pop-Location
    Write-Host "       Node 依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "       Node 依赖已存在" -ForegroundColor Green
}

# ════════════════════════════════════════
# 5. 数据库初始化
# ════════════════════════════════════════
Write-Host "`n[5/6] 数据库初始化..." -ForegroundColor Yellow

# MySQL 建库建表
if ($useWsl) {
    wsl -e bash -c `
        "mysql -u root -p123456 -e 'CREATE DATABASE IF NOT EXISTS attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;' 2>/dev/null; ``
        mysql -u root -p123456 attendance -e 'CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL, date DATE NOT NULL, check_in DATETIME DEFAULT NULL, check_out DATETIME DEFAULT NULL, duration INT DEFAULT NULL, INDEX idx_date (date), INDEX idx_name (name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;' 2>/dev/null; ``
        mysql -u root -p123456 attendance -e 'CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;' 2>/dev/null"
} else {
    & $mysqlCmd -u root -p123456 -e "CREATE DATABASE IF NOT EXISTS attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>$null
    & $mysqlCmd -u root -p123456 attendance -e "CREATE TABLE IF NOT EXISTS attendance (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL, date DATE NOT NULL, check_in DATETIME DEFAULT NULL, check_out DATETIME DEFAULT NULL, duration INT DEFAULT NULL, INDEX idx_date (date), INDEX idx_name (name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;" 2>$null
    & $mysqlCmd -u root -p123456 attendance -e "CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;" 2>$null
}
Write-Host "       MySQL attendance 库就绪" -ForegroundColor Green

# PostgreSQL 建库 + pgvector 扩展
if ($useWsl) {
    wsl -e bash -c `
        "sudo -u postgres psql -p 5434 -c \"CREATE DATABASE face_db;\" 2>/dev/null; ``
        sudo -u postgres psql -p 5434 -d face_db -c \"CREATE EXTENSION IF NOT EXISTS vector;\" 2>/dev/null; ``
        sudo -u postgres psql -p 5434 -d face_db -c 'CREATE TABLE IF NOT EXISTS face_embeddings (id SERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL, file_path TEXT, embedding vector(512), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);' 2>/dev/null"
} else {
    $env:PGPASSWORD = "123456"
    & $psqlCmd -U postgres -p 5434 -c "CREATE DATABASE face_db;" 2>$null
    & $psqlCmd -U postgres -p 5434 -d face_db -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>$null
    & $psqlCmd -U postgres -p 5434 -d face_db -c "CREATE TABLE IF NOT EXISTS face_embeddings (id SERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL, file_path TEXT, embedding vector(512), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);" 2>$null
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
Write-Host "       PostgreSQL face_db 库就绪" -ForegroundColor Green

# ════════════════════════════════════════
# 6. 注册人脸 (可选)
# ════════════════════════════════════════
Write-Host "`n[6/6] 人脸注册..." -ForegroundColor Yellow

$employeesDir = Join-Path $root "employees"
if (Test-Path $employeesDir) {
    $faces = Get-ChildItem $employeesDir -Filter *.jpg -Recurse
    if ($faces.Count -gt 0) {
        $pythonExe = Join-Path $venv "Scripts\python.exe"

        Write-Host "       录入员工信息..." -ForegroundColor Gray
        $names = @()
        foreach ($f in $faces) {
            $name = (Split-Path $f.Directory -Leaf) -replace '^\d+_', ''
            if ($names -notcontains $name) { $names += $name }
        }
        foreach ($n in $names) {
            if ($useWsl) {
                wsl -e bash -c "mysql -u root -p123456 attendance -e \"INSERT IGNORE INTO employees (name) VALUES ('$n');\" 2>/dev/null"
            } else {
                & $mysqlCmd -u root -p123456 attendance -e "INSERT IGNORE INTO employees (name) VALUES ('$n');" 2>$null
            }
        }
        Write-Host "       已录入 $($names.Count) 位员工" -ForegroundColor Green

        Write-Host "       注册人脸向量..." -ForegroundColor Gray
        & $pythonExe -c "
import sys; sys.path.insert(0, r'$root')
from core.face_db import FaceDatabase
from core.vector_db import VectorDB
db = FaceDatabase()
vdb = VectorDB()
count = 0
for name, emb in db.load_all():
    vdb.insert(name, '', emb)
    count += 1
print(f'已注册 {count} 张人脸向量')
"
        Write-Host "       人脸注册完成" -ForegroundColor Green
    } else {
        Write-Host "       未找到员工照片, 请将照片放入 $employeesDir" -ForegroundColor DarkYellow
    }
} else {
    Write-Host "       未找到 employees 目录, 请创建并放入员工照片" -ForegroundColor DarkYellow
}

Write-Host @"

========================================
  部署完成! 🎉
========================================
  启动方式:

    方式一: 一键启动 (推荐)
      .\start.ps1

    方式二: 手动分步启动
      cd avatar && node server.js
      cd .. && .venv\Scripts\python.exe app.py

    打开浏览器: http://localhost:3456
========================================
"@ -ForegroundColor Cyan