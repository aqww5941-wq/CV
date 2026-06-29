"""项目全局配置"""

import os
import re

from core.env_loader import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _get_int_pair(name: str, default: tuple[int, int]) -> tuple[int, int]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    parts = [part for part in re.split(r"[xX,;\s]+", value.strip()) if part]
    if len(parts) != 2:
        raise ValueError(f"{name} must contain width and height, for example 640x640")
    width, height = (int(parts[0]), int(parts[1]))
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} must be positive, got {width}x{height}")
    return width, height


# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 员工照片目录
EMPLOYEES_DIR = os.path.join(BASE_DIR, "employees")

# 缓存目录
CACHE_DIR = os.path.join(BASE_DIR, "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "face_db.pkl")

# InsightFace 模型名称 (buffalo_l 精度高, buffalo_sc 速度快)
INSIGHTFACE_MODEL = os.getenv("INSIGHTFACE_MODEL", "buffalo_l")

# InsightFace 检测输入尺寸，独立于摄像头采集分辨率。
# 480x480 速度优先，640x640 平衡，800x800+ 更适合远距离小脸。
INSIGHTFACE_DET_SIZE = _get_int_pair("INSIGHTFACE_DET_SIZE", (640, 640))

# GPU 加速: True 使用 CUDA, False 使用 CPU
USE_GPU = _get_bool("USE_GPU", False)

# ONNX Runtime 执行提供器 (根据 USE_GPU 自动选择)
INSIGHTFACE_PROVIDERS = (
    ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if USE_GPU
    else ["CPUExecutionProvider"]
)

# 人脸匹配阈值 (cosine similarity, 0~1, 越高越严格)
# ACCEPT_THRESHOLD: 高于此值进入正常签到投票; REVIEW_THRESHOLD: 灰区走多帧复核; 低于直接 unknown。
MATCH_ACCEPT_THRESHOLD = _get_float(
    "MATCH_ACCEPT_THRESHOLD", _get_float("MATCH_THRESHOLD", 0.62)
)
MATCH_REVIEW_THRESHOLD = _get_float("MATCH_REVIEW_THRESHOLD", 0.52)
MATCH_PERSON_TOP_K = _get_int("MATCH_PERSON_TOP_K", 3)
# 保留旧配置名给已有模块/脚本兼容，语义等同“直接接受阈值”。
MATCH_THRESHOLD = MATCH_ACCEPT_THRESHOLD

# 防抖时间 (秒): 同一个人在此时间内只欢迎一次
DEBOUNCE_SECONDS = _get_int("DEBOUNCE_SECONDS", 5)

# 签到冷却时间 (秒): 同一个人签到后, 此时间内不再签到
CHECKIN_COOLDOWN_SECONDS = _get_int("CHECKIN_COOLDOWN_SECONDS", 600)

# 已签到人员持续出现在镜头前时，数字人重复反馈的最小间隔
REPEAT_FEEDBACK_COOLDOWN_SECONDS = _get_int("REPEAT_FEEDBACK_COOLDOWN_SECONDS", 15)

# 是否启用 OpenCV 实时预览窗口。False 时仍会读取摄像头并后台识别。
ENABLE_GUI = _get_bool("ENABLE_GUI", False)

# 测试模式: True = 允许重复打卡 (关闭每日去重和防抖)
ALLOW_REPEAT_CHECKIN = _get_bool("ALLOW_REPEAT_CHECKIN", False)

# 摄像头索引
CAMERA_INDEX = _get_int("CAMERA_INDEX", 0)

# 摄像头分辨率
FRAME_WIDTH = _get_int("FRAME_WIDTH", 1280)
FRAME_HEIGHT = _get_int("FRAME_HEIGHT", 720)
CAMERA_BUFFER_SIZE = _get_int("CAMERA_BUFFER_SIZE", 1)

# 检测间隔 (帧): 每 N 帧做一次完整检测, 其余帧走跟踪缓存
# 30 FPS 下 DETECT_INTERVAL=15 约每秒检测 2 次, CPU 降低 80%+
DETECT_INTERVAL = _get_int("DETECT_INTERVAL", 15)

# 检测置信度阈值
DETECTION_THRESHOLD = _get_float("DETECTION_THRESHOLD", 0.5)

# 单帧最多进入识别/签到业务处理的人脸数。
# 多人场景按人脸框面积优先、离画面中心距离其次排序，背景小脸不进入业务流程。
MAX_PROCESS_FACES = _get_int("MAX_PROCESS_FACES", 3)

# 识别质量门槛: 低质量脸只提示，不进入身份匹配/签到
FACE_MIN_MATCH_SIZE = _get_int("FACE_MIN_MATCH_SIZE", 80)
FACE_MIN_DET_SCORE = _get_float("FACE_MIN_DET_SCORE", 0.55)
FACE_EDGE_MARGIN = _get_int("FACE_EDGE_MARGIN", 16)
FACE_MIN_EYE_DISTANCE = _get_float("FACE_MIN_EYE_DISTANCE", 28.0)
FACE_MAX_POSE_IMBALANCE = _get_float("FACE_MAX_POSE_IMBALANCE", 0.45)
UNKNOWN_CACHE_TTL_SECONDS = _get_float("UNKNOWN_CACHE_TTL_SECONDS", 1.0)
UNKNOWN_CACHE_EMBEDDING_DELTA = _get_float("UNKNOWN_CACHE_EMBEDDING_DELTA", 0.08)
UNKNOWN_VISITORS_FILE = os.path.join(CACHE_DIR, "unknown_visitors.pkl")
UNKNOWN_VISITOR_MATCH_THRESHOLD = _get_float("UNKNOWN_VISITOR_MATCH_THRESHOLD", 0.58)
UNKNOWN_VISITOR_UPDATE_COOLDOWN_SECONDS = _get_int(
    "UNKNOWN_VISITOR_UPDATE_COOLDOWN_SECONDS", 300
)
UNKNOWN_ENROLL_MIN_HITS = _get_int("UNKNOWN_ENROLL_MIN_HITS", 5)
UNKNOWN_ENROLL_MAX_EMPLOYEE_SIMILARITY = _get_float(
    "UNKNOWN_ENROLL_MAX_EMPLOYEE_SIMILARITY", 0.45
)
UNKNOWN_ENROLL_MIN_FACE_SIZE = _get_int("UNKNOWN_ENROLL_MIN_FACE_SIZE", 140)
UNKNOWN_ENROLL_MIN_DET_SCORE = _get_float("UNKNOWN_ENROLL_MIN_DET_SCORE", 0.78)
UNKNOWN_ENROLL_MAX_POSE_IMBALANCE = _get_float(
    "UNKNOWN_ENROLL_MAX_POSE_IMBALANCE", 0.30
)

# ── 人脸跟踪器后端 ──
# opencv: 检测 + IoU 关联 + OpenCV 单目标轻跟踪 (KCF/CSRT/MIL)
# bytetrack: 检测 + Kalman 滤波预测 + IoU 贪心关联 (track_id 更稳定)
TRACKER_BACKEND = os.getenv("TRACKER_BACKEND", "opencv")

# OpenCV 轻跟踪器: KCF/CSRT 需要 opencv-contrib-python，MIL 通常随 opencv-python 可用
OPENCV_TRACKER_TYPE = os.getenv("OPENCV_TRACKER_TYPE", "KCF")

# ByteTrack 检测间隔 (帧): 每 N 帧做一次完整检测, 其余帧走 Kalman 预测
# ByteTrack 建议 3-5 帧, 太低会削弱 track_id 稳定性优势
BYTETRACK_DETECT_INTERVAL = _get_int("BYTETRACK_DETECT_INTERVAL", 3)

# ByteTrack track 缓冲: 丢失多少帧后彻底移除 track
BYTETRACK_TRACK_BUFFER = _get_int("BYTETRACK_TRACK_BUFFER", 30)

# ByteTrack 匹配阈值: IoU 高于此值才认为同一 track
BYTETRACK_MATCH_THRESHOLD = _get_float("BYTETRACK_MATCH_THRESHOLD", 0.3)

# 多帧投票: 连续 N 帧识别结果投票, 避免单帧误识别 (眨眼/侧脸/模糊/运动)
VOTE_WINDOW = _get_int("VOTE_WINDOW", 4)  # 滑动窗口大小
VOTE_MIN_VOTES = _get_int("VOTE_MIN_VOTES", 2)  # 获胜者至少需要 N 票

# ── MySQL 数据库连接配置 (业务数据: 考勤记录) ──
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = _get_int("MYSQL_PORT", 3306)
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "attendance")
MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")
MYSQL_POOL_SIZE = _get_int("MYSQL_POOL_SIZE", 5)

# ── PostgreSQL + pgvector 连接配置 (向量数据: 人脸特征) ──
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = _get_int("PG_PORT", 5434)
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_DATABASE = os.getenv("PG_DATABASE", "face_db")
PG_POOL_SIZE = _get_int("PG_POOL_SIZE", 5)

# ── Redis 连接配置 (签到去重) ──
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = _get_int("REDIS_PORT", 6379)
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = _get_int("REDIS_DB", 0)
REDIS_POOL_SIZE = _get_int("REDIS_POOL_SIZE", 10)
REDIS_POOL_MAX_OVERFLOW = _get_int("REDIS_POOL_MAX_OVERFLOW", 5)

# ── 消息队列配置 (事件发布) ──
MQ_TOPIC_PREFIX = os.getenv("MQ_TOPIC_PREFIX", "attendance")

# ── 数字人前端 ──
AVATAR_SERVER_URL = os.getenv("AVATAR_SERVER_URL", "http://localhost:3456")

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
TTS_QUEUE_MAXSIZE = _get_int("TTS_QUEUE_MAXSIZE", 32)
AUDIO_QUEUE_MAXSIZE = _get_int("AUDIO_QUEUE_MAXSIZE", 16)

# ── 豆包实时语音交互 ──
ENABLE_REALTIME_DIALOG = _get_bool("ENABLE_REALTIME_DIALOG", False)
REALTIME_DIALOG_BASE_URL = os.getenv(
    "REALTIME_DIALOG_BASE_URL",
    "wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
)
REALTIME_DIALOG_APP_ID = os.getenv("REALTIME_DIALOG_APP_ID", "")
REALTIME_DIALOG_ACCESS_KEY = os.getenv("REALTIME_DIALOG_ACCESS_KEY", "")
REALTIME_DIALOG_RESOURCE_ID = os.getenv(
    "REALTIME_DIALOG_RESOURCE_ID",
    "volc.speech.dialog",
)
REALTIME_DIALOG_SPEAKER = os.getenv(
    "REALTIME_DIALOG_SPEAKER",
    "zh_female_xiaohe_jupiter_bigtts",
)
REALTIME_DIALOG_OUTPUT_FORMAT = os.getenv("REALTIME_DIALOG_OUTPUT_FORMAT", "pcm_s16le")
REALTIME_DIALOG_BOT_NAME = os.getenv("REALTIME_DIALOG_BOT_NAME", "前台小助手")
REALTIME_DIALOG_SYSTEM_ROLE = os.getenv(
    "REALTIME_DIALOG_SYSTEM_ROLE",
    "你是公司前台数字人，性格开朗、亲切、有一点害羞。你正在接待来访者和同事。",
)
REALTIME_DIALOG_SPEAKING_STYLE = os.getenv(
    "REALTIME_DIALOG_SPEAKING_STYLE",
    "回复要简短自然，每次一到两句话，像真人前台一样温柔活泼，不要长篇解释。",
)
REALTIME_DIALOG_CITY = os.getenv("REALTIME_DIALOG_CITY", "北京")
REALTIME_DIALOG_RECV_TIMEOUT = _get_int("REALTIME_DIALOG_RECV_TIMEOUT", 10)
REALTIME_DIALOG_SAY_HELLO = _get_bool("REALTIME_DIALOG_SAY_HELLO", False)
REALTIME_DIALOG_RELEASE_GRACE_SECONDS = _get_float(
    "REALTIME_DIALOG_RELEASE_GRACE_SECONDS",
    0.8,
)
REALTIME_DIALOG_INPUT_SAMPLE_RATE = _get_int("REALTIME_DIALOG_INPUT_SAMPLE_RATE", 16000)
REALTIME_DIALOG_INPUT_CHUNK = _get_int("REALTIME_DIALOG_INPUT_CHUNK", 3200)
REALTIME_DIALOG_OUTPUT_SAMPLE_RATE = _get_int(
    "REALTIME_DIALOG_OUTPUT_SAMPLE_RATE", 24000
)
REALTIME_DIALOG_OUTPUT_CHUNK = _get_int("REALTIME_DIALOG_OUTPUT_CHUNK", 3200)

# ── 每日数字人语录生成 ──
DAILY_TTS_TEXTS_FILE = os.getenv(
    "DAILY_TTS_TEXTS_FILE",
    os.path.join(CACHE_DIR, "daily_tts_texts.json"),
)
DAILY_QUOTES_MODEL = os.getenv("DAILY_QUOTES_MODEL", "qwen3.6-flash-2026-04-16")
DAILY_QUOTES_API_BASE = os.getenv(
    "DAILY_QUOTES_API_BASE",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).rstrip("/")
DAILY_QUOTES_API_KEY = os.getenv("DAILY_QUOTES_API_KEY", "")
DAILY_QUOTES_TIMEOUT_SECONDS = _get_float("DAILY_QUOTES_TIMEOUT_SECONDS", 60.0)
DAILY_QUOTES_TEMPERATURE = _get_float("DAILY_QUOTES_TEMPERATURE", 0.9)

# 长时间无人阈值 (秒): 超过此时间触发 idle_long 事件
IDLE_LONG_THRESHOLD = _get_int("IDLE_LONG_THRESHOLD", 60)

# 多人同时出现阈值 (人脸数): 超过此数量触发 crowd 事件
CROWD_THRESHOLD = _get_int("CROWD_THRESHOLD", 3)

# 陌生人触发保护: 半脸/边缘脸/小脸不触发陌生人
STRANGER_MIN_FACE_SIZE = _get_int("STRANGER_MIN_FACE_SIZE", 80)
STRANGER_EDGE_MARGIN = _get_int("STRANGER_EDGE_MARGIN", 16)
STRANGER_MIN_UNKNOWN_HITS = _get_int("STRANGER_MIN_UNKNOWN_HITS", 2)
