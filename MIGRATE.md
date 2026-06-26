# 项目迁移指南

> 从一台 Windows 机器迁移到另一台 Windows 机器，无需 GitHub。

---

## 一、源机器：复制文件

### 1.1 复制整个项目文件夹

把 `CV\` 目录完整复制到目标机器，但**排除以下目录**（不要复制）：

| 排除 | 原因 |
|---|---|
| `.venv\` | 虚拟环境路径硬编码，换机器即失效 |
| `avatar\node_modules\` | 可能有原生模块兼容问题，重新安装更稳 |
| `.git\` | 不需要 git 历史的话可以排除 |

### 1.2 压缩命令（推荐）

在源机器上生成压缩包：

```powershell
# 排除 .venv、node_modules、.git
Compress-Archive -Path "d:\CV\*" `
  -DestinationPath "d:\CV_migrate.zip" `
  -Exclude ".venv", "node_modules", ".git"
```

---

## 二、目标机器：前置准备

### 2.1 安装基础软件

| 软件 | 下载 | 说明 |
|---|---|---|
| Python 3.10+ | https://python.org | 安装时勾选 "Add to PATH" |
| Node.js 16+ | https://nodejs.org | 选 LTS 版本 |
| 摄像头驱动 | 厂家自带 | 确保摄像头可用 |

### 2.2 安装数据库（三选一）

#### 方案 A：本地安装（推荐，无 WSL）

| 数据库 | 下载 | 安装注意 |
|---|---|---|
| MySQL 8.0+ | https://dev.mysql.com/downloads/installer/ | 选 Server only，root 密码设为 `123456` |
| PostgreSQL 14+ | https://www.postgresql.org/download/windows/ | postgres 密码设为 `123456`，端口改为 `5434` |
| Redis | https://github.com/tporadowski/redis/releases | 下载 `.msi`，安装后自动注册为 Windows 服务 |

#### 方案 B：WSL + Ubuntu

```powershell
wsl --install
```

进 WSL 后：

```bash
sudo apt update && sudo apt install -y mysql-server redis-server postgresql postgresql-contrib
```

#### 方案 C：Docker Desktop

```powershell
docker run -d --name mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=123456 -e MYSQL_DATABASE=attendance mysql:8.0
docker run -d --name postgres -p 5434:5432 -e POSTGRES_PASSWORD=123456 -e POSTGRES_DB=face_db pgvector/pgvector:pg16
docker run -d --name redis -p 6379:6379 redis:7
```

### 2.3 数据库配置确认

| 数据库 | 端口 | 用户 | 密码 | 库名 |
|---|---|---|---|---|
| MySQL | 3306 | root | 123456 | attendance |
| PostgreSQL | 5434 | postgres | 123456 | face_db |
| Redis | 6379 | - | 无密码 | db 0 |

---

## 三、目标机器：部署

### 3.1 解压项目

```powershell
Expand-Archive -Path "d:\CV_migrate.zip" -DestinationPath "d:\"
```

### 3.2 运行部署脚本

```powershell
cd d:\CV
.\deploy.ps1
```

脚本会自动：

1. 检测 Python / Node.js 是否安装
2. 检测数据库（WSL 或本地 Windows 服务），自动启动
3. 创建 Python 虚拟环境 + 安装依赖（清华源）
4. 安装 Node 依赖（淘宝源）
5. 初始化数据库（建库建表）
6. 注册员工人脸向量

---

## 四、启动

```powershell
cd d:\CV
.\start.ps1
```

会自动：

- 启动数据库服务
- 启动 Node 数字人前端（端口 3456）
- 启动 Python 人脸识别
- Edge 全屏打开数字人页面

---

## 五、常见问题

### Q: `.\deploy.ps1` 报 "无法加载文件"

PowerShell 默认禁止运行脚本，执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Q: MySQL 连接失败

检查 MySQL 服务是否运行：

```powershell
Get-Service -Name "MySQL*" | Select Name, Status
```

### Q: PostgreSQL 连接失败 (pgvector 扩展)

手动安装 pgvector：

```powershell
# 以管理员身份运行
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -p 5434 -d face_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

如果 pgvector 未安装，下载：https://github.com/pgvector/pgvector

### Q: 摄像头没有画面

- 检查摄像头是否被其他程序占用
- 修改 `config.py` 中的 `CAMERA_INDEX`（0 或 1）
- 运行 `python -c "import cv2; print(cv2.VideoCapture(0).read())"` 测试

### Q: 想要添加新员工

在 `employees\` 下新建目录放入照片，然后：

```powershell
& .venv\Scripts\python.exe tools\capture_faces.py
```

### Q: 想要清除数据重新开始

```powershell
& .venv\Scripts\python.exe tools\clear_records.py
```

---

## 六、快速验证清单

部署完成后，逐项验证：

- [ ] 摄像头画面正常
- [ ] 人脸检测到后数字人有反应（微笑/打招呼）
- [ ] 签到成功，MySQL 有记录
- [ ] 签退成功，语音播放 "明天见"
- [ ] 重复签到有提示
- [ ] 陌生人出现有反应
- [ ] 长时间无人，数字人进入待机
- [ ] 多人同时出现，数字人做出反应
- [ ] 待机状态下微表情和小动作正常
- [ ] 刷新页面背景随机切换