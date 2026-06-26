# AI 智慧前台数字人

> 基于人脸识别+Live2D的智能考勤前台数字人，自动打招呼、签到签退、响应多人场景。

## 📋 环境要求

- **Python 3.8+**
- **Node.js 16+**
- **WSL2 + Ubuntu** (Windows 上推荐，预装 MySQL/Redis/PostgreSQL)
- **摄像头**

## ⚡ 一键部署

直接运行：

```powershell
.\deploy.ps1
```

脚本会自动：

1. 环境检查
2. 启动 WSL 里的 MySQL/Redis/PostgreSQL
3. 创建 Python 虚拟环境 + 安装依赖
4. 安装 Node 依赖
5. 初始化数据库（建库建表）
6. 注册已有员工人脸向量

## 🚀 一键启动

部署完成后，任何时候启动：

```powershell
.\start.ps1
```

会自动：

- 启动 WSL 数据库服务
- 启动 Node 数字人前端（端口 3456）
- 启动 Python 人脸识别服务
- Edge 全屏打开 `?display` 纯净模式

## 📁 目录结构

```
CV/
├── app.py                # 主程序: 人脸检测+事件触发
├── config.py             # 全局配置
├── requirements.txt      # Python 依赖
├── start.ps1             # 一键启动脚本
├── deploy.ps1            # 一键部署脚本 (GitHub 新环境)
├── rebuild_venv.ps1      # 重建 Python 环境
├── core/
│   ├── attendance_db.py  # MySQL 考勤记录
│   ├── vector_db.py      # PostgreSQL + pgvector 人脸向量
│   ├── redis_checkin.py  # Redis 签到去重
│   ├── events.py         # 事件总线 → 推送给数字人
│   ├── sound.py          # Edge TTS 语音 + pygame 播放
│   ├── recognizer.py     # 人脸识别
│   └── ...
├── avatar/               # 数字人前端 (Live2D)
│   ├── index.html        # 主页面 (三背景随机)
│   ├── demo.html         # 表情动作调试
│   ├── server.js         # Node 服务 (端口 3456)
│   ├── models/Epsilon/   # Live2D 模型
│   └── ...
├── tools/
│   ├── clear_records.py  # 清除数据工具
│   └── capture_faces.py  # 捕捉人脸向量
├── employees/            # 员工照片 (按人分目录)
│   ├── 张三/
│   │   ├── 001.jpg
│   │   └── 002.jpg
│   └── ...
└── cache/               # TTS 缓存 / face_db 缓存
```

## 🎨 背景主题

- 每次刷新随机：梦幻气泡 / 天空渐变 / 樱花飘落
- PIXI 透明背景，CSS 渐变透出，UI 自适应浅色风格

## 🔧 功能

| 功能 | 说明 |
|---|---|
| 每日签到去重 | Redis 缓存，防止重复签到 |
| 陌生人检测 | 陌生人欢迎 |
| 重复签到提醒 | 已经签过还会打打招呼 |
| 多人事件 | 多人同时出现，数字人做出反应 |
| 长时间无人 | 触发 idle_long 事件，温柔提醒 |
| 待机循环 | 微表情 + 小动作自动随机 |
| Edge TTS | 预生成缓存，毫秒级播放 |
| MySQL 考勤 | 完整记录签到/签退/时长 |
| PostgreSQL + pgvector | 人脸特征向量存储，余弦相似度检索 |

## 📝 数据库配置

项目依赖三个数据库，都在 WSL 里：

| 服务 | 端口 | 库名 | 用户 | 密码 |
|---|---|---|---|---|
| MySQL | 3306 | attendance | root | 123456 |
| PostgreSQL | 5434 | face_db | postgres | 123456 |
| Redis | 6379 | 0 | - | 无 |

在 WSL 里手动安装：

```bash
sudo apt update
sudo apt install -y mysql-server redis-server postgresql postgresql-contrib postgresql-server-dev-all
sudo -u postgres psql -p 5434 -c "ALTER USER postgres PASSWORD '123456';"
```

## 👤 添加新员工

在 `employees/` 新建目录：

```
employees/
└── 姓名/
    ├── 001.jpg
    └── 002.jpg
```

然后：

```powershell
& .venv\Scripts\python.exe tools\capture_faces.py
```

会自动提取人脸向量，存入 PostgreSQL。

## 🧹 清理数据

```powershell
& .venv\Scripts\python.exe tools\clear_records.py
```

按提示选择清除哪些数据。

## 🔍 查看 Redis 缓存

```bash
wsl -e redis-cli --raw KEYS "checkin:*"
```

## 📊 查看 MySQL 考勤

```bash
wsl -e mysql -u root -p123456 attendance -e "SELECT name, check_in FROM attendance WHERE date = CURDATE();"
```

## 📝 依赖清单

**Python:**
- opencv-python - 图像处理
- insightface - 人脸识别
- numpy - 向量运算
- onnxruntime-gpu / onnxruntime - 模型推理
- Pillow - UI 渲染
- pymysql - MySQL
- psycopg2-binary - PostgreSQL
- pgvector - 向量检索
- redis - 签到去重
- edge-tts - 语音合成
- pygame - 音频播放

**Node:**
- express - 静态文件服务
- ws - WebSocket 事件推送

## 📄 License

MIT