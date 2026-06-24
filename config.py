"""项目全局配置"""

import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 员工照片目录
EMPLOYEES_DIR = os.path.join(BASE_DIR, "employees")

# 缓存目录
CACHE_DIR = os.path.join(BASE_DIR, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "face_db.pkl")

# InsightFace 模型名称 (buffalo_l 精度高, buffalo_sc 速度快)
INSIGHTFACE_MODEL = "buffalo_l"

# 人脸匹配阈值 (cosine similarity, 0~1, 越高越严格)
MATCH_THRESHOLD = 0.6

# 防抖时间 (秒): 同一个人在此时间内只欢迎一次
DEBOUNCE_SECONDS = 5

# 是否启用摄像头实时画面（暂时关闭设为 False）
ENABLE_CAMERA = False

# 测试模式: True = 允许重复打卡 (关闭每日去重和防抖)
ALLOW_REPEAT_CHECKIN = False

# 摄像头索引
CAMERA_INDEX = 0

# 摄像头分辨率
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

# 检测间隔 (帧): 每 N 帧做一次完整检测, 其余帧走跟踪缓存
# 30 FPS 下 DETECT_INTERVAL=15 约每秒检测 2 次, CPU 降低 80%+
DETECT_INTERVAL = 15

# 检测置信度阈值
DETECTION_THRESHOLD = 0.5

# 多帧投票: 连续 N 帧识别结果投票, 避免单帧误识别 (眨眼/侧脸/模糊/运动)
VOTE_WINDOW = 5  # 滑动窗口大小
VOTE_MIN_VOTES = 3  # 获胜者至少需要 N 票

# ── MySQL 数据库连接配置 ──
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "123456"
MYSQL_DATABASE = "attendance"
MYSQL_CHARSET = "utf8mb4"

# UI 颜色 (BGR)
COLOR_RECOGNIZED = (0, 255, 0)  # 绿色: 识别成功
COLOR_STRANGER = (0, 0, 255)  # 红色: 陌生人
COLOR_WELCOME = (255, 255, 0)  # 青色: 欢迎文字
COLOR_BOX = (0, 255, 0)  # 人脸框颜色
