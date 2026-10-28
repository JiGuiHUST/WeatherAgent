# -*- coding: utf-8 -*-
"""全局配置：气象Token、BASE_URL、路径常量"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ===================== 加载 .env（LLM 凭据、气象 Token 等）=====================
_ENV_FILE = os.path.join(BASE_DIR, ".env")


def _load_env_file(path):
    """无 python-dotenv 时的兜底解析：把 KEY=VALUE 写入 os.environ（不覆盖已有变量）"""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            for raw in fp:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except OSError:
        pass


# Dedicated local Huafeng credentials; excluded from Git and delivery archives.
_load_env_file(os.path.join(BASE_DIR, '.env.weathercn.local'))

try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE)
except Exception:
    _load_env_file(_ENV_FILE)  # 未安装 python-dotenv 时兜底

# ===================== 气象接口配置 =====================
BASE_URL = "http://180.149.156.4:8001"
# 凭据从 .env / 环境变量读取，避免硬编码到源码（参见 .env.example）
WEATHER_TOKEN = os.getenv("WEATHER_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {WEATHER_TOKEN}"}

# ===================== 路径常量 =====================
DATA_DIR = os.path.join(BASE_DIR, "data")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
WEATHER_IMG_DIR = os.path.join(STATIC_DIR, "weather_img")
LOG_DIR = os.path.join(BASE_DIR, "logs")

CITY_BBOX_FILE = os.path.join(DATA_DIR, "city_bbox.json")
TRAVEL_SPOTS_FILE = os.path.join(DATA_DIR, "travel_spots.json")

# 确保运行期目录存在
for _d in (WEATHER_IMG_DIR, LOG_DIR):
    os.makedirs(_d, exist_ok=True)

# ===================== 业务常量 =====================
PREFERENCES = ["首次旅行", "情侣旅行", "亲子", "美食打卡", "徒步海岛", "历史人文"]

# 季节 -> 示例月份（用于季节输入时取默认样本日期）
SEASON_MONTH = {"春季": 4, "夏季": 7, "秋季": 10, "冬季": 1}

# 偏好 -> 对应的景点分类优先级
PREFERENCE_CATEGORY_PRIORITY = {
    "首次旅行": ["文化地标", "城市海滩", "亲子乐园", "海岛活动"],
    "情侣旅行": ["海岛活动", "城市海滩", "文化地标", "亲子乐园"],
    "亲子": ["亲子乐园", "城市海滩", "海岛活动", "文化地标"],
    "美食打卡": ["城市海滩", "文化地标", "海岛活动", "亲子乐园"],
    "徒步海岛": ["海岛活动", "城市海滩", "文化地标", "亲子乐园"],
    "历史人文": ["文化地标", "城市海滩", "亲子乐园", "海岛活动"],
}

# Flask
_secret_path = os.path.join(BASE_DIR, ".session_secret")
if not os.path.exists(_secret_path):
    import secrets
    try:
        with open(_secret_path, "x", encoding="utf-8") as _fp:
            _fp.write(secrets.token_hex(32))
    except FileExistsError:
        pass
with open(_secret_path, encoding="utf-8") as _fp:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or _fp.read().strip()
DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))

# ===================== LLM 配置（OpenAI 兼容接口）=====================
# 凭据从 .env / 环境变量读取，避免硬编码到源码
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://10.104.160.105/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen3-14B")
LLM_TIMEOUT = 25
LLM_MAX_TOKENS = 1400
LLM_ENABLED = bool(LLM_API_KEY)

# Huafeng is activated only after a real key/permission probe, never by a mock test.
WEATHER_PROVIDER = os.getenv("WEATHER_PROVIDER", "auto").lower()
WEATHERCN_OPENAPI_KEY = os.getenv("WEATHERCN_OPENAPI_KEY", "")
WEATHERCN_ENABLED = os.getenv("WEATHERCN_ENABLED", "0") == "1"
