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

# GPU 加速: True 使用 CUDA, False 使用 CPU
USE_GPU = False

# ONNX Runtime 执行提供器 (根据 USE_GPU 自动选择)
INSIGHTFACE_PROVIDERS = (
    ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if USE_GPU
    else ["CPUExecutionProvider"]
)

# 人脸匹配阈值 (cosine similarity, 0~1, 越高越严格)
MATCH_THRESHOLD = 0.6

# 防抖时间 (秒): 同一个人在此时间内只欢迎一次
DEBOUNCE_SECONDS = 5

# 签到冷却时间 (秒): 同一个人签到后, 此时间内不再签到
CHECKIN_COOLDOWN_SECONDS = 600

# 已签到人员持续出现在镜头前时，数字人重复反馈的最小间隔
REPEAT_FEEDBACK_COOLDOWN_SECONDS = 15

# 是否启用 OpenCV 实时预览窗口。False 时仍会读取摄像头并后台识别。
ENABLE_GUI = False

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

# ── MySQL 数据库连接配置 (业务数据: 考勤记录) ──
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "123456"
MYSQL_DATABASE = "attendance"
MYSQL_CHARSET = "utf8mb4"

# ── PostgreSQL + pgvector 连接配置 (向量数据: 人脸特征) ──
PG_HOST = "127.0.0.1"
PG_PORT = 5434
PG_USER = "postgres"
PG_PASSWORD = "123456"
PG_DATABASE = "face_db"

# ── Redis 连接配置 (签到去重) ──
REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_PASSWORD = ""
REDIS_DB = 0

# ── 消息队列配置 (事件发布) ──
MQ_BACKEND = "redis"  # "redis" | "kafka" | "rabbitmq"
MQ_TOPIC_PREFIX = "attendance"

# ── 数字人前端 ──
AVATAR_SERVER_URL = "http://localhost:3456"

# ── 语音队列与缓存 ──
TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
TTS_VOICE_BY_MODEL = {
    "epsilon": os.getenv("TTS_VOICE_EPSILON", "zh-CN-XiaoyiNeural"),
    "chitose": os.getenv("TTS_VOICE_CHITOSE", "zh-CN-YunxiNeural"),
    "haruGreeter": os.getenv("TTS_VOICE_HARU_GREETER", "zh-CN-XiaoyiNeural"),
    "haru": os.getenv("TTS_VOICE_HARU", "zh-CN-XiaoxiaoNeural"),
    "natori": os.getenv("TTS_VOICE_NATORI", "zh-TW-YunJheNeural"),
}
TTS_CACHE_DIR = os.path.join(CACHE_DIR, "tts")
TTS_QUEUE_MAXSIZE = 32
AUDIO_QUEUE_MAXSIZE = 16

# 长时间无人阈值 (秒): 超过此时间触发 idle_long 事件
IDLE_LONG_THRESHOLD = 60

# 多人同时出现阈值 (人脸数): 超过此数量触发 crowd 事件
CROWD_THRESHOLD = 3

# 陌生人触发保护: 半脸/边缘脸/小脸不触发陌生人
STRANGER_MIN_FACE_SIZE = 110
STRANGER_EDGE_MARGIN = 24
STRANGER_MIN_UNKNOWN_HITS = 3
