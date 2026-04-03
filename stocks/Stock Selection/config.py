"""
股票分析系统配置文件
"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
MONITOR_FILE = PROJECT_ROOT / "watchlist.json"
ALERTS_FILE = PROJECT_ROOT / "monitor_alerts.json"

# 确保目录存在
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ==================== Tushare 配置 ====================
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "f44ca4afe1b57594c870c3f7048a0f0464e47533205b2c2136381f7d")

# Tushare API 基础配置
TUSHARE_BASE_URL = "http://api.tushare.pro"

# ==================== 数据源优先级 ====================
# 0: Tushare (优先), 1: AKShare (备选), 2: Baostock (最后备选)
DATA_SOURCE_PRIORITY = ["tushare", "akshare", "baostock"]

# ==================== 选股默认参数 ====================
SCREENER_DEFAULTS = {
    # 市场范围
    "market": "全市场",  # 全市场 / 创业板 / 科创板 / 主板

    # 技术面参数
    "ma_short": 5,       # 短期均线天数
    "ma_medium": 10,     # 中期均线天数
    "ma_long": 20,      # 长期均线天数
    "ma多头排列": True,  # 是否要求均线多头排列

    "macd_require_above_zero": True,  # MACD是否要求在0轴上方
    "turnover_rate_min": 3.0,         # 最小换手率%
    "volume_ratio_min": 1.0,          # 最小量比（放宽以获取更多候选）

    # 涨停基因：10日内有涨停
    "limit_up_gen": True,
    "limit_up_days": 10,

    # 基本面参数
    "市值_min": 50,        # 亿元
    "市价_max": 200,       # 元（排除高价股）

    "毛利率_min": 15,      # %
    "净利润增长_min": 0,  # %（正增长）

    # 评分权重
    "weights": {
        "技术面": 0.40,
        "基本面": 0.30,
        "情绪面": 0.30,
    }
}

# ==================== 分析默认参数 ====================
ANALYZER_DEFAULTS = {
    # 均线参数
    "ma_params": [5, 10, 20, 60],

    # MACD参数
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    # KDJ参数
    "kdj_n": 9,
    "kdj_m1": 3,
    "kdj_m2": 3,

    # BOLL参数
    "boll_period": 20,
    "boll_std": 2,

    # 止损止盈
    "止损比例": 0.05,   # 5%
    "止盈比例": 0.15,   # 15%

    # 超买超卖
    "RSI_overbought": 70,
    "RSI_oversold": 30,
}

# ==================== 监控默认参数 ====================
MONITOR_DEFAULTS = {
    # 检查间隔（分钟）
    "check_interval": 30,

    # 触发条件
    "trigger_on": {
        "价格突破": True,
        "均线金叉死叉": True,
        "MACD交叉": True,
        "成交量异常": True,
        "到达止损止盈位": True,
    },

    # 阈值
    "volume_spike_ratio": 2.0,  # 量能异常放大倍数
    "price_change_threshold": 0.03,  # 价格变化阈值3%
}

# ==================== K线形态识别 ====================
KLINE_PATTERNS = {
    # 看多形态
    "看多": [
        "早晨之星", "锤子线", "吞没形态", "红三兵",
        "多方炮", "曙光初现", "旭日东升", "上升抵抗",
        "缩量下跌", "放量上涨",
    ],
    # 看空形态
    "看空": [
        "黄昏之星", "射击之星", "吞没形态", "黑三兵",
        "空方炮", "乌云盖顶", "倾盆大雨", "吊颈线",
        "放量滞涨", "缩量上涨",
    ],
    # 中性形态
    "中性": [
        "十字星", "螺旋桨", "孕线", "孕十字",
    ]
}

# ==================== 板块/概念映射 ====================
SECTOR_MAP = {
    "新能源": ["锂电池", "光伏", "储能", "电动车"],
    "科技": ["半导体", "芯片", "人工智能", "软件"],
    "消费": ["白酒", "食品", "家电", "旅游"],
    "医药": ["医疗器械", "生物医药", "中药", "疫苗"],
    "金融": ["银行", "保险", "证券", "多元金融"],
    "周期": ["钢铁", "煤炭", "有色", "化工", "建材"],
}

# ==================== 常用股票代码前缀 ====================
MARKET_PREFIX = {
    "sh": "上证主板",
    "sz": "深证主板",
    "cy": "创业板",
    "kc": "科创板",
    "bj": "北交所",
}
