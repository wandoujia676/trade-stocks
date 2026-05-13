"""
数据获取层 - Tushare + AKShare 双数据源，自动降级
支持缓存机制减少API调用
"""
import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

import pandas as pd
import numpy as np

from config import (
    CACHE_DIR, TUSHARE_TOKEN, DATA_SOURCE_PRIORITY,
    TUSHARE_BASE_URL
)

logger = logging.getLogger(__name__)


class DataSourceError(Exception):
    """数据源异常"""
    pass


# 【v9.1 Step 4】指数代码映射：symbol(无后缀) → Tushare ts_code(带市场后缀)
# 股票 daily 和指数 index_daily 是两个接口，指数走这张表路由。
# 注意：000001 在股票（平安银行 .SZ）和指数（上证 .SH）里都存在，无后缀时按个股优先；
# 想拉上证指数必须用 "000001.SH"。其他指数代码股票里无冲突，无后缀也可识别。
INDEX_CODE_MAP = {
    "000001.SH": "000001.SH",   # 上证指数（必须带后缀）
    "000300": "000300.SH",      # 沪深300
    "000905": "000905.SH",      # 中证500
    "000906": "000906.SH",      # 中证800
    "000016": "000016.SH",      # 上证50
    "399001": "399001.SZ",      # 深证成指
    "399006": "399006.SZ",      # 创业板指
    "399005": "399005.SZ",      # 中小板指
    "000688": "000688.SH",      # 科创50
}

# AKShare 新浪源指数符号（绕开东财反爬）
AKSHARE_INDEX_SYMBOL = {
    "000001.SH": "sh000001",
    "000300.SH": "sh000300",
    "000905.SH": "sh000905",
    "000906.SH": "sh000906",
    "000016.SH": "sh000016",
    "399001.SZ": "sz399001",
    "399006.SZ": "sz399006",
    "399005.SZ": "sz399005",
    "000688.SH": "sh000688",
}


def is_index_code(symbol: str) -> bool:
    """判断 symbol 是否为指数代码。
    - 带后缀（如 000001.SH）：在 INDEX_CODE_MAP values 中算指数
    - 无后缀：在 INDEX_CODE_MAP keys 中且 key 不带后缀才算（消歧 000001）
    """
    if not symbol:
        return False
    s = symbol.strip().upper()
    if "." in s:
        return s in INDEX_CODE_MAP.values()
    # 无后缀：必须在 keys 里且 key 也不含后缀
    return s in INDEX_CODE_MAP and "." not in s


def to_index_ts_code(symbol: str) -> str:
    """无后缀 symbol → 完整 ts_code（含市场后缀）"""
    s = symbol.strip().upper()
    if "." in s:
        return s
    return INDEX_CODE_MAP.get(s, s)



class DataQualityError(Exception):
    """数据质量异常：失败率超阈值，不是真的没数据而是数据层大面积失败"""
    pass


def akshare_retry(func):
    """AKShare 网络层重试：3 次，1s/2s/4s 指数退避。仅重试网络类异常。"""
    import time as _time
    import functools
    from requests.exceptions import ConnectionError as _ReqConnErr, Timeout as _ReqTimeout
    from http.client import RemoteDisconnected as _RemoteDisconnected
    from urllib3.exceptions import ProtocolError as _ProtocolError

    RETRY_EXC = (_ReqConnErr, _ReqTimeout, _RemoteDisconnected, _ProtocolError, OSError)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        delays = [1, 2, 4]
        last_exc = None
        for i, delay in enumerate(delays):
            try:
                return func(*args, **kwargs)
            except RETRY_EXC as e:
                last_exc = e
                if i < len(delays) - 1:
                    logger.debug(
                        f"AKShare 重试 {i+1}/{len(delays)} ({func.__name__}): "
                        f"{type(e).__name__}，{delay}s 后再试"
                    )
                    _time.sleep(delay)
            except DataSourceError as e:
                # 看底层异常是不是网络类，是就重试
                cause = e.__cause__ or e.__context__
                if isinstance(cause, RETRY_EXC):
                    last_exc = e
                    if i < len(delays) - 1:
                        logger.debug(
                            f"AKShare 重试 {i+1}/{len(delays)} ({func.__name__}): "
                            f"{type(cause).__name__}（被 DataSourceError 包装），{delay}s 后再试"
                        )
                        _time.sleep(delay)
                        continue
                raise
        raise last_exc
    return wrapper


class DataCache:
    """SQLite本地缓存"""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = cache_dir / "stock_data.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS data_cache (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_updated
                ON data_cache(updated_at)
            """)

    def get(self, key: str, max_age_minutes: int = 60):
        """获取缓存数据，如果过期返回None（支持 DataFrame 和 dict）"""
        import io
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data, updated_at FROM data_cache WHERE key = ?",
                (key,)
            ).fetchone()

            if row is None:
                return None

            data_json, updated_at = row
            updated_time = datetime.fromisoformat(updated_at)
            age = (datetime.now() - updated_time).total_seconds() / 60

            if age > max_age_minutes:
                return None

            if data_json.startswith('__dict__:'):
                return json.loads(data_json[9:])
            return pd.read_json(io.StringIO(data_json))

    def set(self, key: str, data):
        """设置缓存（支持 DataFrame 和 dict）"""
        if isinstance(data, dict):
            serialized = '__dict__:' + json.dumps(data, ensure_ascii=False, default=str)
        else:
            serialized = data.to_json()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO data_cache (key, data, updated_at) VALUES (?, ?, ?)",
                (key, serialized, datetime.now().isoformat())
            )

    def clear_expired(self, max_age_minutes: int = 1440):
        """清除过期缓存（默认24小时）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM data_cache WHERE updated_at < datetime('now', ?)",
                (f"-{max_age_minutes} minutes",)
            )


class TushareFetcher:
    """Tushare数据获取器（带频率限制）"""

    def __init__(self, token: str = None):
        self.token = token or TUSHARE_TOKEN
        self.pro = None
        self._last_call_time = 0
        self._min_interval = 1.2  # 最小请求间隔（秒），留余量
        if self.token:
            try:
                import tushare as ts
                self.pro = ts.pro_api(self.token)
            except ImportError:
                logger.warning("Tushare未安装")

    def is_available(self) -> bool:
        return bool(self.token and self.pro)

    def _rate_limit(self):
        """频率限制：确保请求间隔"""
        import time
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    def get_daily(self, ts_code: str = None, trade_date: str = None,
                  start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取日线数据"""
        if not self.is_available():
            raise DataSourceError("Tushare不可用")

        try:
            self._rate_limit()
            if trade_date:
                df = self.pro.daily(ts_code=ts_code, trade_date=trade_date)
            else:
                df = self.pro.daily(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date
                )
            return df
        except Exception as e:
            logger.error(f"Tushare get_daily失败: {e}")
            raise DataSourceError(f"Tushare API错误: {e}")

    def get_index_daily(self, ts_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """【v9.1 Step 4】获取指数日线（走 pro.index_daily，与个股 pro.daily 是两个接口）"""
        if not self.is_available():
            raise DataSourceError("Tushare不可用")

        try:
            self._rate_limit()
            df = self.pro.index_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )
            return df
        except Exception as e:
            logger.error(f"Tushare index_daily失败: {e}")
            raise DataSourceError(f"Tushare API错误: {e}")

    def get_realtime_quote(self, ts_codes: List[str]) -> pd.DataFrame:
        """实时行情（需要积分）"""
        if not self.is_available():
            raise DataSourceError("Tushare不可用")

        try:
            import tushare as ts
            df = ts.realtime_quote(ts_code=ts_codes)
            return df
        except Exception as e:
            logger.error(f"Tushare realtime_quote失败: {e}")
            raise DataSourceError(f"Tushare API错误: {e}")

    def get_stock_basic(self, ts_code: str = None) -> pd.DataFrame:
        """股票基本信息"""
        if not self.is_available():
            raise DataSourceError("Tushare不可用")

        try:
            import tushare as ts
            pro = ts.pro_api(self.token)
            df = pro.stock_basic(ts_code=ts_code)
            return df
        except Exception as e:
            logger.error(f"Tushare stock_basic失败: {e}")
            raise DataSourceError(f"Tushare API错误: {e}")

    def get_fina_indicator(self, ts_code: str, start_date: str = None) -> pd.DataFrame:
        """财务指标（需要积分）"""
        if not self.is_available():
            raise DataSourceError("Tushare不可用")

        try:
            import tushare as ts
            pro = ts.pro_api(self.token)
            df = pro.fina_indicator(ts_code=ts_code, start_date=start_date)
            return df
        except Exception as e:
            logger.warning(f"Tushare fina_indicator需要积分或不可用: {e}")
            raise DataSourceError("需要Tushare Pro积分")


class AKShareFetcher:
    """AKShare数据获取器（免费备选）"""

    def __init__(self):
        self.api = None
        try:
            import akshare as ak
            self.api = ak
        except ImportError:
            logger.warning("AKShare未安装")

        # 【v9.1】批量行情缓存，给 get_stock_info 用
        # 避免 50 只股票 × 50 次 stock_individual_info_em 调用被东财限流
        self._market_spot_cache: Optional[pd.DataFrame] = None
        self._market_spot_cache_time: Optional[datetime] = None
        self._market_spot_cache_ttl = 300  # 5 分钟
        # 【v9.1】spot 失败冷却期：东财拒连后 5 分钟内不再尝试，避免 50 只股票重复白耗 20 分钟
        self._market_spot_failed_at: Optional[datetime] = None
        self._market_spot_cooldown = 300  # 5 分钟

        # 【v9.1】代码+名称表缓存（非东财源，东财 spot 被拒时的兜底）
        self._code_name_cache: Optional[pd.DataFrame] = None
        self._code_name_cache_time: Optional[datetime] = None
        self._code_name_cache_ttl = 86400  # 1 天（名称几乎不变）

    def is_available(self) -> bool:
        return self.api is not None

    def _get_market_spot_cached(self) -> Optional[pd.DataFrame]:
        """【v9.1】全市场实时行情批量缓存（5 分钟）

        一次调用拿到 5000+ 只股票的代码/名称/总市值/流通市值/市盈率-动态/市净率 等，
        替代按只调 stock_individual_info_em（那个东财反爬得死）。
        东财今天反爬严重时，这个也可能失败，失败时进入 5 分钟冷却，不再尝试。
        """
        now = datetime.now()
        if (self._market_spot_cache is not None
                and self._market_spot_cache_time is not None
                and (now - self._market_spot_cache_time).total_seconds() < self._market_spot_cache_ttl):
            return self._market_spot_cache

        # 【v9.1】失败冷却期内直接跳过，不要让 50 只股票各等 20s 重试
        if (self._market_spot_failed_at is not None
                and (now - self._market_spot_failed_at).total_seconds() < self._market_spot_cooldown):
            return None

        try:
            df = self._ak_market_spot()
            if df is not None and not df.empty:
                # 代码列统一成字符串，便于查询
                if '代码' in df.columns:
                    df['代码'] = df['代码'].astype(str).str.zfill(6)
                self._market_spot_cache = df
                self._market_spot_cache_time = now
                self._market_spot_failed_at = None
                logger.info(f"【v9.1】全市场批量行情缓存刷新：{len(df)} 只")
                return df
        except Exception as e:
            logger.debug(f"AKShare 全市场批量行情获取失败（东财 push2 被拒），进入 5 分钟冷却: {e}")
            self._market_spot_failed_at = now
        return self._market_spot_cache  # 返回旧缓存兜底（即使过期）

    def _get_code_name_cached(self) -> Optional[pd.DataFrame]:
        """【v9.1】A 股代码+名称表（stock_info_a_code_name，非东财源，1 天缓存）

        东财 spot 被拒时的名称兜底。只能填 code/name，市值/PE 等字段缺失，
        下游 screener 的 low_priority 分支会兜住。
        """
        now = datetime.now()
        if (self._code_name_cache is not None
                and self._code_name_cache_time is not None
                and (now - self._code_name_cache_time).total_seconds() < self._code_name_cache_ttl):
            return self._code_name_cache

        try:
            df = self._ak_code_name()
            if df is not None and not df.empty:
                # 标准化代码列（可能叫 code 或 symbol）
                code_col = 'code' if 'code' in df.columns else ('symbol' if 'symbol' in df.columns else df.columns[0])
                if code_col != 'code':
                    df = df.rename(columns={code_col: 'code'})
                df['code'] = df['code'].astype(str).str.zfill(6)
                self._code_name_cache = df
                self._code_name_cache_time = now
                logger.info(f"【v9.1】A 股代码+名称表缓存刷新：{len(df)} 只（兜底）")
                return df
        except Exception as e:
            logger.debug(f"AKShare 代码+名称表获取失败: {e}")
        return self._code_name_cache

    @staticmethod
    @akshare_retry
    def _ak_market_spot() -> Optional[pd.DataFrame]:
        """AKShare 全市场实时行情（带网络重试）"""
        import akshare as ak
        return ak.stock_zh_a_spot_em()

    @staticmethod
    @akshare_retry
    def _ak_code_name() -> Optional[pd.DataFrame]:
        """AKShare 代码+名称表（带网络重试，非东财源）"""
        import akshare as ak
        return ak.stock_info_a_code_name()

    @akshare_retry
    def get_realtime_data(self, symbol: str = "000001") -> pd.DataFrame:
        """获取实时行情（AKShare股票实时行情）"""
        if not self.is_available():
            raise DataSourceError("AKShare不可用")

        try:
            # symbol格式: 000001.sz 或 600000.sh
            if not symbol.startswith(("0", "6", "3", "8", "4", "8")):
                symbol = self._convert_code(symbol)

            df = self.api.stock_zh_a_spot_em()
            if symbol:
                df = df[df['代码'] == symbol.replace(".sh", "").replace(".sz", "")]
            return df
        except Exception as e:
            logger.error(f"AKShare realtime失败: {e}")
            raise DataSourceError(f"AKShare API错误: {e}")

    @akshare_retry
    def get_daily(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取日线数据"""
        if not self.is_available():
            raise DataSourceError("AKShare不可用")

        try:
            symbol = self._convert_code(symbol)
            # 【v9.0 修复】period 固定为 daily，不要根据时间跨度自动切换周线/月线
            # 原逻辑会导致回测时拉 365 天数据变成月线，只返回 12 行
            period = "daily"

            df = self.api.stock_zh_a_hist(
                symbol=symbol.split(".")[0],
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            return df
        except Exception as e:
            logger.error(f"AKShare daily失败: {e}")
            raise DataSourceError(f"AKShare API错误: {e}")

    @akshare_retry
    def get_index_daily(self, symbol_ak: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """【v9.1 Step 4】获取指数日线（AKShare 新浪源，避开东财反爬）
        symbol_ak: 形如 'sh000300' / 'sz399001'，由调用方通过 AKSHARE_INDEX_SYMBOL 映射得到
        start_date/end_date: 形如 '20260101'
        """
        if not self.is_available():
            raise DataSourceError("AKShare不可用")

        try:
            df = self.api.stock_zh_index_daily(symbol=symbol_ak)
            if df is None or df.empty:
                return df
            # 过滤日期范围（sina 接口返回全历史）
            if start_date or end_date:
                df = df.copy()
                df['date'] = pd.to_datetime(df['date'])
                if start_date:
                    df = df[df['date'] >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df['date'] <= pd.to_datetime(end_date)]
                df = df.reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"AKShare index_daily失败: {e}")
            raise DataSourceError(f"AKShare API错误: {e}")

    @akshare_retry
    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """获取股票基本信息

        【v9.1 改造】三级降级：
        1. 全市场批量行情 spot 缓存（stock_zh_a_spot_em） → 拿到全量字段（名称/市值/PE/市净率/换手率/量比）
        2. 代码+名称表缓存（stock_info_a_code_name，非东财源） → 只填 name，但绝不失败
        3. 单只接口（stock_individual_info_em） → 最后兜底（东财拒的时候也会挂，但试一次）

        理由：东财 push2 子域今天大面积拒连，spot 批量也可能挂。用 code_name 兜名称字段，
        市值/PE 等字段缺失时下游 screener 的 low_priority 分支会兜住，不会崩。
        """
        if not self.is_available():
            raise DataSourceError("AKShare不可用")

        symbol_clean = self._convert_code(symbol).split(".")[0].zfill(6)

        # ========== 第 1 级：全市场 spot 批量缓存 ==========
        spot = self._get_market_spot_cached()
        if spot is not None and not spot.empty and '代码' in spot.columns:
            matched = spot[spot['代码'] == symbol_clean]
            if not matched.empty:
                row = matched.iloc[0]

                def _fmt_cap(val):
                    try:
                        v = float(val)
                        if v > 0:
                            return f"{v / 1e8:.2f}亿"
                    except (TypeError, ValueError):
                        pass
                    return ""

                info = {
                    '股票简称': str(row.get('名称', '')),
                    '股票名称': str(row.get('名称', '')),
                    '名称': str(row.get('名称', '')),
                    'name': str(row.get('名称', '')),
                    '代码': symbol_clean,
                    '最新价': row.get('最新价'),
                    '总市值': _fmt_cap(row.get('总市值')),
                    '流通市值': _fmt_cap(row.get('流通市值')),
                    '市盈率': row.get('市盈率-动态'),
                    '市净率': row.get('市净率'),
                    '换手率': row.get('换手率'),
                    '量比': row.get('量比'),
                }
                return {k: v for k, v in info.items() if v not in (None, '', 'nan')}

        # ========== 第 2 级：代码+名称表兜底（非东财源）==========
        names = self._get_code_name_cached()
        if names is not None and not names.empty:
            matched = names[names['code'] == symbol_clean]
            if not matched.empty:
                name = str(matched.iloc[0].get('name', ''))
                if name:
                    logger.debug(f"{symbol_clean}: spot 未命中，用 code_name 兜底（仅名称）")
                    return {
                        '股票简称': name,
                        '股票名称': name,
                        '名称': name,
                        'name': name,
                        '代码': symbol_clean,
                    }

        # ========== 第 3 级：单只接口（最后兜底，东财拒的时候也会挂）==========
        # 如果 spot 正在冷却期（说明东财 push2 整条线都拒了），单只接口大概率也失败，
        # 跳过它避免每只股票再浪费 7s 重试，直接返回空 dict 让 screener 走 low_priority 分支
        if self._market_spot_failed_at is not None:
            now = datetime.now()
            if (now - self._market_spot_failed_at).total_seconds() < self._market_spot_cooldown:
                logger.debug(f"{symbol_clean}: spot 冷却中，跳过单只接口兜底")
                return {}

        try:
            logger.debug(f"{symbol_clean}: 两级缓存都未命中，调单只接口兜底")
            df = self.api.stock_individual_info_em(symbol=symbol_clean)
            info = dict(zip(df['item'], df['value']))
            return info
        except Exception as e:
            logger.debug(f"AKShare info 全部失败 {symbol}: {e}")
            # 下游已经做了 "if not info: low_priority" 的降级处理（screener.py:775），
            # 返回空 dict 比抛异常更友好，不会让整个批次崩
            return {}

    def get_market_board(self) -> pd.DataFrame:
        """获取板块/概念行情"""
        if not self.is_available():
            raise DataSourceError("AKShare不可用")

        try:
            df = self.api.stock_board_concept_name_em()
            return df
        except Exception as e:
            logger.error(f"AKShare board失败: {e}")
            raise DataSourceError(f"AKShare API错误: {e}")

    def _convert_code(self, code: str) -> str:
        """将简化的股票代码转换为AKShare格式"""
        code = code.strip()
        if "." in code:
            return code
        if code.startswith(("6", "5")):
            return f"{code}.sh"
        if code.startswith(("0", "1", "3")):
            return f"{code}.sz"
        if code.startswith(("4", "8")):
            return f"{code}.bj"
        return code


class BaostockFetcher:
    """Baostock数据获取器（最后备选）"""

    def __init__(self):
        self.api = None
        try:
            import baostock as bs
            bs.login()
            self.api = bs
        except ImportError:
            logger.warning("Baostock未安装")
        except Exception as e:
            logger.warning(f"Baostock登录失败: {e}")

    def __del__(self):
        if self.api:
            try:
                self.api.logout()
            except:
                pass

    def is_available(self) -> bool:
        return self.api is not None

    def get_daily(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取日线数据"""
        if not self.is_available():
            raise DataSourceError("Baostock不可用")

        try:
            import baostock as bs
            # 转换代码格式: 000001.sz -> sz.000001
            if "." in symbol:
                market, code = symbol.split(".")
                bs_code = f"{market}.{code}"
            else:
                if symbol.startswith("6"):
                    bs_code = f"sh.{symbol}"
                else:
                    bs_code = f"sz.{symbol}"

            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,volume,amount,turn",
                start_date=start_date, end_date=end_date,
                frequency="d"
            )

            data = []
            while (rs.error_code == '0') & rs.next():
                data.append(rs.get_row_data())
            df = pd.DataFrame(data, columns=rs.fields)
            return df
        except Exception as e:
            logger.error(f"Baostock daily失败: {e}")
            raise DataSourceError(f"Baostock API错误: {e}")

    def get_stock_basic(self) -> pd.DataFrame:
        """获取所有股票基本信息"""
        if not self.is_available():
            raise DataSourceError("Baostock不可用")

        try:
            import baostock as bs
            rs = bs.query_all_stock()
            data = []
            while (rs.error_code == '0') & rs.next():
                data.append(rs.get_row_data())
            df = pd.DataFrame(data, columns=rs.fields)
            return df
        except Exception as e:
            logger.error(f"Baostock basic失败: {e}")
            raise DataSourceError(f"Baostock API错误: {e}")


class DataFetcher:
    """
    统一数据获取器 - 支持多数据源自动降级
    优先级: Tushare -> AKShare -> Baostock
    """

    def __init__(self):
        self.cache = DataCache()
        # 【v9.0 Step 3b 修复】按需初始化数据源，避免不在优先级列表里的源（如 baostock）
        # 在 __init__ 阶段就 login() 卡住网络
        self.fetchers = {}
        if "tushare" in DATA_SOURCE_PRIORITY:
            self.fetchers["tushare"] = TushareFetcher()
        if "akshare" in DATA_SOURCE_PRIORITY:
            self.fetchers["akshare"] = AKShareFetcher()
        if "baostock" in DATA_SOURCE_PRIORITY:
            self.fetchers["baostock"] = BaostockFetcher()
        self.current_source = None
        self._moneyflow_rank_cache = None
        self._moneyflow_rank_cache_time = None
        self._yjyg_cache = None
        self._yjyg_cache_time = None
        self._detect_available_source()

    def _detect_available_source(self):
        """检测可用的数据源"""
        for source_name in DATA_SOURCE_PRIORITY:
            fetcher = self.fetchers.get(source_name)
            if fetcher and fetcher.is_available():
                self.current_source = source_name
                logger.info(f"使用数据源: {source_name}")
                return
        logger.warning("未检测到可用数据源，请安装tushare/akshare/baostock")

    def _get_moneyflow_rank_cached(self) -> Optional[pd.DataFrame]:
        """获取全市场资金流向排名（批量缓存，5分钟有效期）"""
        now = datetime.now()
        if (self._moneyflow_rank_cache is not None
                and self._moneyflow_rank_cache_time is not None
                and (now - self._moneyflow_rank_cache_time).total_seconds() < 300):
            return self._moneyflow_rank_cache

        try:
            df = self._ak_moneyflow_rank()
            if df is not None and not df.empty:
                self._moneyflow_rank_cache = df
                self._moneyflow_rank_cache_time = now
                return df
        except Exception as e:
            logger.debug(f"AKShare全市场资金流向获取失败: {e}")
        return self._moneyflow_rank_cache

    @staticmethod
    @akshare_retry
    def _ak_moneyflow_rank() -> Optional[pd.DataFrame]:
        """AKShare 全市场资金流向排名（带网络重试）"""
        import akshare as ak
        return ak.stock_individual_fund_flow_rank(indicator='今日')

    @staticmethod
    @akshare_retry
    def _ak_individual_fund_flow(stock: str, market: str) -> Optional[pd.DataFrame]:
        """【v9.1 Step 5】AKShare 单股资金流向（批量排名接口挂时兜底）
        stock: 如 '000001' / '600036'
        market: 'sz' 或 'sh'
        """
        import akshare as ak
        return ak.stock_individual_fund_flow(stock=stock, market=market)

    def _get_yjyg_cached(self) -> Optional[pd.DataFrame]:
        """获取全市场业绩预告（批量缓存，1天有效期）

        【v9.1 Step 5】修复季度日期：只取 "<= now" 的最新季末会得到 4 行（当期预告还没批量
        披露）。改为依次尝试最近 4 期季末，合并所有返回数据，再按股票代码取最新一条。
        这样覆盖 Q1 披露期的跨季公告，也兜底去年 Q4 年报预告。
        """
        now = datetime.now()
        if (self._yjyg_cache is not None
                and self._yjyg_cache_time is not None
                and (now - self._yjyg_cache_time).total_seconds() < 86400):
            return self._yjyg_cache

        try:
            # 生成最近 4 期季末日期（含未到的本季，AKShare 会返回已披露部分）
            quarter_ends = [(3, 31), (6, 30), (9, 30), (12, 31)]
            candidates: List[str] = []
            y, m = now.year, now.month
            # 从本季倒序 4 期
            for qm, qd in reversed(quarter_ends):
                candidates.append(f"{y}{qm:02d}{qd:02d}")
            # 再加上一年的全部 4 期（凑够 4+4=8 候选，取数据最多那期及合并）
            for qm, qd in reversed(quarter_ends):
                candidates.append(f"{y - 1}{qm:02d}{qd:02d}")
            # 去掉明显未来超过 3 个月的日期（不合理）
            cutoff = now + timedelta(days=90)
            candidates = [d for d in candidates if datetime.strptime(d, "%Y%m%d") <= cutoff]

            dfs: List[pd.DataFrame] = []
            for q in candidates[:6]:  # 最多 6 期，防止过度请求
                try:
                    df = self._ak_yjyg(q)
                    if df is not None and not df.empty:
                        dfs.append(df)
                        # 若已累计足够多行（有效性高）就停
                        if sum(len(x) for x in dfs) >= 500:
                            break
                except Exception as e:
                    logger.debug(f"AKShare yjyg {q} 获取失败: {e}")
                    continue

            if dfs:
                merged = pd.concat(dfs, ignore_index=True)
                # 同一股票保留最新一条（假设接口按 公告日/报告期 排序，取 drop_duplicates first）
                if '股票代码' in merged.columns:
                    merged = merged.drop_duplicates(subset=['股票代码'], keep='first')
                self._yjyg_cache = merged
                self._yjyg_cache_time = now
                return merged
        except Exception as e:
            logger.debug(f"AKShare业绩预告获取失败: {e}")
        return self._yjyg_cache

    @staticmethod
    @akshare_retry
    def _ak_yjyg(quarter_date: str) -> Optional[pd.DataFrame]:
        """AKShare 业绩预告（带网络重试）"""
        import akshare as ak
        return ak.stock_yjyg_em(date=quarter_date)

    def get_daily(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        获取日线数据（自动降级）
        symbol: 股票代码，如 "000001" 或 "000001.sz"
        """
        # 默认取近90个交易日
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")

        cache_key = f"daily_{symbol}_{start_date}_{end_date}"

        # 尝试从缓存获取
        if use_cache:
            cached = self.cache.get(cache_key, max_age_minutes=60)
            if cached is not None and not cached.empty:
                return cached

        # 【v9.1 Step 4】指数代码走 index_daily 接口（与个股 daily 是两个接口）
        is_index = is_index_code(symbol)

        # 尝试各数据源
        errors = []
        for source_name in DATA_SOURCE_PRIORITY:
            fetcher = self.fetchers.get(source_name)
            if not fetcher or not fetcher.is_available():
                continue

            try:
                if source_name == "tushare":
                    if is_index:
                        ts_code = to_index_ts_code(symbol)
                        df = fetcher.get_index_daily(
                            ts_code=ts_code,
                            start_date=start_date,
                            end_date=end_date,
                        )
                    else:
                        df = fetcher.get_daily(
                            ts_code=self._to_tushare_code(symbol),
                            start_date=start_date,
                            end_date=end_date
                        )
                    if df is not None and not df.empty:
                        # 统一列名
                        df = self._normalize_daily_df(df, source_name)
                        df['source'] = 'tushare'
                        # Tushare返回降序（最新在前），转为升序以便iloc[-1]取最新
                        if 'trade_date' in df.columns:
                            df = df.sort_values('trade_date').reset_index(drop=True)
                        self.cache.set(cache_key, df)
                        self.current_source = source_name
                        return df

                elif source_name == "akshare":
                    if is_index:
                        # 【v9.1 Step 4】指数走 AKShare 新浪源（绕开东财反爬）
                        ts_code = to_index_ts_code(symbol)
                        ak_sym = AKSHARE_INDEX_SYMBOL.get(ts_code)
                        if not ak_sym:
                            continue
                        df = fetcher.get_index_daily(ak_sym, start_date, end_date)
                    else:
                        df = fetcher.get_daily(symbol, start_date, end_date)
                    if df is not None and not df.empty:
                        # 统一列名
                        df = self._normalize_daily_df(df, source_name)
                        df['source'] = 'akshare'
                        # AKShare返回的是升序，不需要排序
                        self.cache.set(cache_key, df)
                        self.current_source = source_name
                        return df

                elif source_name == "baostock":
                    df = fetcher.get_daily(symbol, start_date, end_date)
                    if df is not None and not df.empty:
                        df = self._normalize_daily_df(df, source_name)
                        df['source'] = 'baostock'
                        # Baostock返回的是升序，不需要排序
                        self.cache.set(cache_key, df)
                        self.current_source = source_name
                        return df

            except (DataSourceError, Exception) as e:
                errors.append(f"{source_name}: {e}")
                continue

        raise DataSourceError(f"所有数据源均失败: {errors}")

    def get_realtime(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时行情（单股）- 使用新浪/腾讯实时接口

        返回关键字段的字典
        """
        symbol = symbol.strip()

        # ✅ 优先使用新浪/腾讯实时接口（真正的盘中实时数据）
        try:
            realtime_data = self.get_realtime_spot(symbol)
            if realtime_data and realtime_data.get('current', 0) > 0:
                return {
                    "code": symbol,
                    "name": realtime_data.get('name', ''),
                    "price": float(realtime_data.get('current', 0)),
                    "change_pct": float(realtime_data.get('pct_chg', 0)),
                    "volume": float(realtime_data.get('volume', 0)),
                    "amount": float(realtime_data.get('amount', 0)),
                    "high": float(realtime_data.get('high', 0)),
                    "low": float(realtime_data.get('low', 0)),
                    "open": float(realtime_data.get('open', 0)),
                    "prev_close": float(realtime_data.get('close_prev', 0)),
                    "turnover": 0,
                    "source": realtime_data.get('source', 'realtime')
                }
        except Exception as e:
            logger.warning(f"实时接口获取失败，降级到日线数据: {e}")

        # ⚠️ 降级: 使用Tushare日线数据（盘后或实时接口失败时）
        try:
            if self.fetchers["tushare"] and self.fetchers["tushare"].is_available():
                ts_code = self._to_tushare_code(symbol)
                df = self.fetchers["tushare"].get_daily(ts_code=ts_code)
                if df is not None and not df.empty:
                    latest = df.iloc[0]
                    return {
                        "code": symbol,
                        "name": "",
                        "price": float(latest.get("close", 0)),
                        "change_pct": float(latest.get("pct_change", 0)),
                        "volume": float(latest.get("volume", 0)),
                        "amount": float(latest.get("amount", 0)),
                        "high": float(latest.get("high", 0)),
                        "low": float(latest.get("low", 0)),
                        "open": float(latest.get("open", 0)),
                        "prev_close": float(latest.get("pre_close", 0)),
                        "turnover": float(latest.get("turnover_rate", 0)),
                        "source": "tushare"
                    }
        except Exception:
            pass

        return {}

    def get_realtime_batch(self, codes: List[str]) -> pd.DataFrame:
        """
        批量获取实时行情 - 使用新浪/腾讯实时接口

        Args:
            codes: 股票代码列表

        Returns:
            DataFrame with realtime data for all codes
        """
        try:
            from realtime_fetcher import get_realtime_fetcher
            fetcher = get_realtime_fetcher()
            return fetcher.get_spot(codes)
        except Exception as e:
            logger.error(f"批量获取实时行情失败: {e}")
            return pd.DataFrame()

    def get_realtime_batch_as_dict(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        批量获取实时行情 - 返回字典格式

        返回 {代码: 行情字典}
        """
        results = {}

        # ✅ 优先使用新浪/腾讯实时接口
        try:
            spots_df = self.get_realtime_batch(symbols)
            if spots_df is not None and not spots_df.empty:
                for _, row in spots_df.iterrows():
                    code = str(row.get('code', '')).zfill(6)
                    results[code] = {
                        "code": code,
                        "name": row.get('name', ''),
                        "price": float(row.get('current', 0)),
                        "change_pct": float(row.get('pct_chg', 0)),
                        "volume": float(row.get('volume', 0)),
                        "amount": float(row.get('amount', 0)),
                        "high": float(row.get('high', 0)),
                        "low": float(row.get('low', 0)),
                        "open": float(row.get('open', 0)),
                        "prev_close": float(row.get('close_prev', 0)),
                        "source": row.get('source', 'realtime')
                    }
                return results
        except Exception as e:
            logger.warning(f"批量实时接口获取失败: {e}")

        # ⚠️ 降级: 使用Tushare日线数据
        batch_size = 200
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            try:
                ts_codes = [self._to_tushare_code(s) for s in batch]
                if self.fetchers["tushare"] and self.fetchers["tushare"].is_available():
                    import tushare as ts
                    pro = ts.pro_api(self.token)
                    self.fetchers["tushare"]._rate_limit()
                    df = pro.daily(ts_code=','.join(ts_codes))
                    if df is not None and not df.empty:
                        for _, row in df.iterrows():
                            code = row['ts_code'].replace('.SH', '').replace('.SZ', '')
                            results[code] = {
                                "code": code,
                                "name": "",
                                "price": float(row.get("close", 0)),
                                "change_pct": float(row.get("pct_change", 0)),
                                "volume": float(row.get("volume", 0)),
                                "high": float(row.get("high", 0)),
                                "low": float(row.get("low", 0)),
                                "open": float(row.get("open", 0)),
                                "source": "tushare"
                            }
            except Exception as e:
                logger.error(f"批量获取失败: {e}")

        return results

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """获取股票基本信息（支持多数据源降级）"""
        for source_name in ["akshare", "baostock"]:
            fetcher = self.fetchers.get(source_name)
            if not fetcher or not fetcher.is_available():
                continue

            try:
                if source_name == "akshare":
                    return fetcher.get_stock_info(symbol)
            except Exception:
                # 捕获所有异常（网络错误、代理错误等），尝试下一个数据源
                continue

        # 所有数据源都失败时，返回空字典（让调用方使用默认值）
        return {}

    def get_index_components(self, index_code: str = "000001") -> List[str]:
        """获取指数成分股（上证指数/深证成指等）"""
        try:
            if self.fetchers["akshare"].is_available():
                df = self.fetchers["akshare"].get_market_board()
                return df['代码'].tolist()[:100] if not df.empty else []
        except:
            pass
        return []

    def get_financial_indicators(self, symbol: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        获取财务指标（基本面）- 小金库 9.0 Step 2

        Args:
            symbol: 股票代码，如 '600519'
            use_cache: 是否使用缓存

        Returns:
            归一化后的财务指标字典:
            - pe: 市盈率（TTM）
            - roe: 净资产收益率（%）
            - net_profit_growth: 净利润增长率（同比，%）
            - debt_ratio: 资产负债率（%）
            - update_date: 数据更新日期

        降级策略: Tushare → AKShare → 空字典
        """
        cache_key = f"financial_{symbol}"

        # 尝试从缓存获取（7天有效期）
        if use_cache:
            cached = self.cache.get(cache_key, max_age_minutes=60 * 24 * 7)
            if cached is not None:
                return cached

        # 尝试 Tushare
        if self.fetchers.get("tushare") and self.fetchers["tushare"].is_available():
            try:
                ts_code = self._to_tushare_code(symbol)
                df = self.fetchers["tushare"].get_fina_indicator(ts_code)

                if df is not None and not df.empty:
                    # 取最新一期数据
                    latest = df.iloc[0]
                    result = self._normalize_financial_dict({
                        'pe_ttm': latest.get('pe_ttm'),
                        'roe': latest.get('roe'),
                        'netprofit_yoy': latest.get('netprofit_yoy'),
                        'debt_to_assets': latest.get('debt_to_assets'),
                        'end_date': latest.get('end_date')
                    }, 'tushare')

                    self.cache.set(cache_key, result)
                    self.current_source = 'tushare'
                    return result
            except Exception as e:
                logger.debug(f"Tushare财务指标获取失败 {symbol}: {e}")

        # 降级到 AKShare
        if self.fetchers.get("akshare") and self.fetchers["akshare"].is_available():
            try:
                import akshare as ak
                # 使用同花顺财务摘要（stock_financial_abstract_ths）
                df = ak.stock_financial_abstract_ths(symbol=symbol)

                if df is not None and not df.empty:
                    latest = df.iloc[-1]  # 最新在最后一行
                    result = self._normalize_financial_dict({
                        '净资产收益率': latest.get('净资产收益率'),
                        '净利润同比增长率': latest.get('净利润同比增长率'),
                        '资产负债率': latest.get('资产负债率'),
                        '报告期': latest.get('报告期'),
                    }, 'akshare')

                    # 【v9.1 Step 5】PE 回补：同花顺接口不含 PE，从 spot 批量缓存里取
                    # （v9.1 已有该缓存，里面含市盈率-动态字段，5 分钟 TTL）
                    if result.get('pe') is None:
                        try:
                            ak_fetcher = self.fetchers.get("akshare")
                            if ak_fetcher and hasattr(ak_fetcher, "_get_market_spot_cached"):
                                spot = ak_fetcher._get_market_spot_cached()
                                if spot is not None and not spot.empty and '代码' in spot.columns:
                                    matched = spot[spot['代码'] == symbol]
                                    if not matched.empty:
                                        pe_val = matched.iloc[0].get('市盈率-动态')
                                        if pe_val is not None and pd.notna(pe_val):
                                            result['pe'] = float(pe_val)
                        except Exception as e:
                            logger.debug(f"PE 从 spot 回补失败 {symbol}: {e}")

                    self.cache.set(cache_key, result)
                    self.current_source = 'akshare'
                    return result
            except Exception as e:
                logger.debug(f"AKShare财务指标获取失败 {symbol}: {e}")

        # 所有数据源都失败，返回空字典
        logger.warning(f"无法获取 {symbol} 的财务指标，跳过基本面维度")
        return {}

    def get_moneyflow(self, symbol: str, days: int = 5, use_cache: bool = True) -> Dict[str, Any]:
        """
        获取资金流向（近N日）- 小金库 9.0 Step 2

        Args:
            symbol: 股票代码，如 '600519'
            days: 统计天数（默认近5日）
            use_cache: 是否使用缓存

        Returns:
            归一化后的资金流向字典:
            - main_net_inflow: 主力资金净流入（近N日累计，单位：万元）
            - super_net_inflow: 超大单净流入（万元）
            - hk_hold_change: 北向资金持股变化（近N日，万股，可能为None）
            - margin_balance_change: 融资余额变化（近N日，万元，可能为None）

        降级策略: Tushare → AKShare → 空字典
        缓存：1天
        """
        cache_key = f"moneyflow_{symbol}_{days}"

        if use_cache:
            cached = self.cache.get(cache_key, max_age_minutes=60 * 24)
            if cached is not None:
                return cached

        # 尝试 Tushare
        if self.fetchers.get("tushare") and self.fetchers["tushare"].is_available():
            try:
                import tushare as ts
                pro = ts.pro_api(self.fetchers["tushare"].token)
                ts_code = self._to_tushare_code(symbol)
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=days * 2 + 5)).strftime("%Y%m%d")

                # 主力资金流向
                df_flow = pro.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)
                main_inflow = None
                super_inflow = None
                if df_flow is not None and not df_flow.empty:
                    df_flow = df_flow.head(days)
                    main_inflow = float(df_flow['net_mf_amount'].sum()) if 'net_mf_amount' in df_flow.columns else None
                    if 'buy_elg_amount' in df_flow.columns and 'sell_elg_amount' in df_flow.columns:
                        super_inflow = float((df_flow['buy_elg_amount'] - df_flow['sell_elg_amount']).sum())

                # 北向资金持股变化（高级接口，可能失败）
                hk_change = None
                try:
                    df_hk = pro.hk_hold(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    if df_hk is not None and not df_hk.empty and len(df_hk) >= 2:
                        hk_change = float(df_hk.iloc[0]['vol'] - df_hk.iloc[-1]['vol']) / 10000
                except Exception:
                    pass

                # 融资余额变化（高级接口，可能失败）
                margin_change = None
                try:
                    df_margin = pro.margin_detail(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    if df_margin is not None and not df_margin.empty and len(df_margin) >= 2:
                        margin_change = float(df_margin.iloc[0]['rzye'] - df_margin.iloc[-1]['rzye']) / 10000
                except Exception:
                    pass

                if main_inflow is not None:
                    result = self._normalize_moneyflow_dict({
                        'main_net_inflow': main_inflow,
                        'super_net_inflow': super_inflow,
                        'hk_hold_change': hk_change,
                        'margin_balance_change': margin_change,
                    }, 'tushare')
                    self.cache.set(cache_key, result)
                    self.current_source = 'tushare'
                    return result
            except Exception as e:
                logger.debug(f"Tushare资金流向获取失败 {symbol}: {e}")

        # 降级到 AKShare（使用全市场批量接口，按代码过滤）
        if self.fetchers.get("akshare") and self.fetchers["akshare"].is_available():
            try:
                df_rank = self._get_moneyflow_rank_cached()
                if df_rank is not None and not df_rank.empty:
                    matched = df_rank[df_rank['代码'].astype(str) == symbol]
                    if not matched.empty:
                        row = matched.iloc[0]
                        main_col = '今日主力净流入-净额'
                        super_col = '今日超大单净流入-净额'

                        main_inflow = float(row[main_col]) / 10000 if pd.notna(row.get(main_col)) else None
                        super_inflow = float(row[super_col]) / 10000 if pd.notna(row.get(super_col)) else None

                        result = self._normalize_moneyflow_dict({
                            'main_net_inflow': main_inflow,
                            'super_net_inflow': super_inflow,
                            'hk_hold_change': None,
                            'margin_balance_change': None,
                        }, 'akshare')
                        self.cache.set(cache_key, result)
                        self.current_source = 'akshare'
                        return result
            except Exception as e:
                logger.debug(f"AKShare资金流向获取失败 {symbol}: {e}")

            # 【v9.1 Step 5】单股级二次降级：排名接口挂/未命中时，调 stock_individual_fund_flow
            # 该接口按股票返回 120 天资金流向日线，网络层活着（诊断 0.4s/只）
            try:
                market = 'sh' if symbol.startswith('6') else 'sz'
                df_ind = self._ak_individual_fund_flow(stock=symbol, market=market)
                if df_ind is not None and not df_ind.empty:
                    # 接口返回升序（最老在前），取最后 days 天
                    recent = df_ind.tail(days) if len(df_ind) >= days else df_ind
                    main_col = '主力净流入-净额'
                    super_col = '超大单净流入-净额'
                    main_inflow = None
                    super_inflow = None
                    if main_col in recent.columns:
                        vals = pd.to_numeric(recent[main_col], errors='coerce').dropna()
                        # 单股接口返回单位是元，转万元
                        main_inflow = float(vals.sum()) / 10000 if len(vals) > 0 else None
                    if super_col in recent.columns:
                        vals = pd.to_numeric(recent[super_col], errors='coerce').dropna()
                        super_inflow = float(vals.sum()) / 10000 if len(vals) > 0 else None

                    if main_inflow is not None:
                        result = self._normalize_moneyflow_dict({
                            'main_net_inflow': main_inflow,
                            'super_net_inflow': super_inflow,
                            'hk_hold_change': None,
                            'margin_balance_change': None,
                        }, 'akshare')
                        self.cache.set(cache_key, result)
                        self.current_source = 'akshare'
                        return result
            except Exception as e:
                logger.debug(f"AKShare单股资金流向获取失败 {symbol}: {e}")

        logger.warning(f"无法获取 {symbol} 的资金流向，跳过资金面维度")
        return {}

    def get_catalysts(self, symbol: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        获取催化剂信息 - 小金库 9.0 Step 2

        Args:
            symbol: 股票代码
            use_cache: 是否使用缓存

        Returns:
            归一化后的催化剂字典:
            - has_forecast: 是否有业绩预告（近3个月）
            - forecast_type: 预告类型（预增/预减/扭亏/首亏/不变/略增/略减）
            - forecast_growth: 预告净利润增长率中值（%，可能为None）
            - has_survey: 是否有机构调研（近1个月）
            - survey_count: 调研机构数量
            - has_policy: 是否有政策利好（从新闻提取）

        降级策略: Tushare → AKShare → NewsFetcher → 空字典
        缓存：3天
        """
        cache_key = f"catalysts_{symbol}"

        if use_cache:
            cached = self.cache.get(cache_key, max_age_minutes=60 * 24 * 3)
            if cached is not None:
                return cached

        result = {
            'has_forecast': False,
            'forecast_type': None,
            'forecast_growth': None,
            'has_survey': False,
            'survey_count': 0,
            'has_policy': False,
        }

        # 尝试 Tushare 获取业绩预告 + 机构调研
        if self.fetchers.get("tushare") and self.fetchers["tushare"].is_available():
            try:
                import tushare as ts
                pro = ts.pro_api(self.fetchers["tushare"].token)
                ts_code = self._to_tushare_code(symbol)
                end_date = datetime.now().strftime("%Y%m%d")
                forecast_start = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
                survey_start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

                # 业绩预告
                try:
                    df_fc = pro.forecast(ts_code=ts_code, start_date=forecast_start, end_date=end_date)
                    if df_fc is not None and not df_fc.empty:
                        latest = df_fc.iloc[0]
                        result['has_forecast'] = True
                        result['forecast_type'] = str(latest.get('type', '')) or None
                        # 取增长率中值
                        p_min = latest.get('p_change_min')
                        p_max = latest.get('p_change_max')
                        if p_min is not None and p_max is not None:
                            result['forecast_growth'] = (float(p_min) + float(p_max)) / 2
                except Exception as e:
                    logger.debug(f"Tushare forecast获取失败 {symbol}: {e}")

                # 机构调研
                try:
                    df_sv = pro.stk_surv(ts_code=ts_code, start_date=survey_start, end_date=end_date)
                    if df_sv is not None and not df_sv.empty:
                        result['has_survey'] = True
                        result['survey_count'] = len(df_sv)
                except Exception as e:
                    logger.debug(f"Tushare stk_surv获取失败 {symbol}: {e}")

            except Exception as e:
                logger.debug(f"Tushare催化剂获取失败 {symbol}: {e}")

        # 降级 AKShare 获取业绩预告（使用 stock_yjyg_em 批量接口）
        if not result['has_forecast'] and self.fetchers.get("akshare") and self.fetchers["akshare"].is_available():
            try:
                df_yg = self._get_yjyg_cached()
                if df_yg is not None and not df_yg.empty:
                    matched = df_yg[df_yg['股票代码'].astype(str) == symbol]
                    if not matched.empty:
                        row = matched.iloc[0]
                        result['has_forecast'] = True
                        result['forecast_type'] = str(row.get('预告类型', ''))
                        growth = row.get('业绩变动幅度')
                        if growth is not None and pd.notna(growth):
                            try:
                                result['forecast_growth'] = float(growth)
                            except (ValueError, TypeError):
                                pass
            except Exception as e:
                logger.debug(f"AKShare业绩预告获取失败 {symbol}: {e}")

        # 政策利好（通过 NewsFetcher 关键词匹配）
        try:
            news_fetcher = get_news_fetcher()
            if news_fetcher.is_available():
                df_news = news_fetcher.get_stock_news(symbol)
                if df_news is not None and not df_news.empty:
                    # 【v9.0 修复】只看最近 10 条，避免太旧的新闻拉高 has_policy 命中率
                    df_news = df_news.head(10)
                    policy_keywords = ['政策', '补贴', '扶持', '支持', '规划', '利好', '获批', '签约', '中标']
                    text_col = '内容' if '内容' in df_news.columns else ('content' if 'content' in df_news.columns else None)
                    if text_col:
                        for _, row in df_news.iterrows():
                            text = str(row[text_col])
                            if any(kw in text for kw in policy_keywords):
                                result['has_policy'] = True
                                break
        except Exception as e:
            logger.debug(f"政策利好检查失败 {symbol}: {e}")

        result = self._normalize_catalyst_dict(result, 'merged')
        self.cache.set(cache_key, result)
        return result

    def _to_tushare_code(self, symbol: str) -> str:
        """转换为tushare格式"""
        symbol = symbol.strip()
        if "." in symbol:
            return symbol.upper()
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        if symbol.startswith(("0", "3")):
            return f"{symbol}.SZ"
        return symbol

    def _normalize_daily_df(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        """统一不同数据源的列名"""
        if df is None or df.empty:
            return df

        # 统一 Tushare 列名
        if source == "tushare":
            rename_map = {
                "vol": "volume",
                "pct_chg": "pct_change",
            }
            df = df.rename(columns=rename_map)

        if source == "akshare":
            rename_map = {
                "日期": "trade_date",
                "股票代码": "ts_code",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "换手率": "turnover_rate",
                "涨跌幅": "pct_change",
                "涨跌额": "change",
                # 【v9.1 Step 4】新浪指数接口英文列
                "date": "trade_date",
            }
            df = df.rename(columns=rename_map)
            # 【v9.1 Step 4】指数接口没 pct_change，从 close 算一个
            if "pct_change" not in df.columns and "close" in df.columns and len(df) > 1:
                df = df.copy()
                df["pct_change"] = df["close"].astype(float).pct_change() * 100

        elif source == "baostock":
            rename_map = {
                "date": "trade_date",
                "code": "ts_code",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
                "amount": "amount",
                "turn": "turnover_rate",
            }
            df = df.rename(columns=rename_map)
            if 'pct_change' not in df.columns and 'close' in df.columns:
                df['pct_change'] = df['close'].pct_change() * 100

        # 确保数值列是数值类型
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_change']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    def _parse_pct_value(self, val) -> Optional[float]:
        """解析可能带%/亿后缀的数值"""
        if val is None or val is False or val == '-' or val == '':
            return None
        s = str(val).strip().replace('%', '').replace('亿', '')
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    def _normalize_financial_dict(self, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """
        统一不同数据源的财务指标字段名 - 小金库 9.0 Step 2

        Args:
            data: 原始数据字典
            source: 数据源名称 ('tushare' or 'akshare')

        Returns:
            归一化后的字典，统一字段名为: pe, roe, net_profit_growth, debt_ratio, update_date
        """
        result = {}

        if source == 'tushare':
            result['pe'] = float(data.get('pe_ttm', 0)) if data.get('pe_ttm') else None
            result['roe'] = float(data.get('roe', 0)) if data.get('roe') else None
            result['net_profit_growth'] = float(data.get('netprofit_yoy', 0)) if data.get('netprofit_yoy') else None
            result['debt_ratio'] = float(data.get('debt_to_assets', 0)) if data.get('debt_to_assets') else None
            result['update_date'] = data.get('end_date', '')

        elif source == 'akshare':
            # stock_financial_abstract_ths 返回带%后缀的字符串
            result['pe'] = None  # 此数据源不含PE，由调用方补充
            result['roe'] = self._parse_pct_value(data.get('净资产收益率'))
            result['net_profit_growth'] = self._parse_pct_value(data.get('净利润同比增长率'))
            result['debt_ratio'] = self._parse_pct_value(data.get('资产负债率'))
            result['update_date'] = str(data.get('报告期', ''))

        return result

    def _normalize_moneyflow_dict(self, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """
        统一资金流向字段名 - 小金库 9.0 Step 2

        统一字段：main_net_inflow, super_net_inflow, hk_hold_change, margin_balance_change
        单位：万元 / 万股
        """
        return {
            'main_net_inflow': float(data['main_net_inflow']) if data.get('main_net_inflow') is not None else None,
            'super_net_inflow': float(data['super_net_inflow']) if data.get('super_net_inflow') is not None else None,
            'hk_hold_change': float(data['hk_hold_change']) if data.get('hk_hold_change') is not None else None,
            'margin_balance_change': float(data['margin_balance_change']) if data.get('margin_balance_change') is not None else None,
        }

    def _normalize_catalyst_dict(self, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """
        统一催化剂字段名 - 小金库 9.0 Step 2

        统一字段：has_forecast, forecast_type, forecast_growth, has_survey, survey_count, has_policy
        forecast_type 标准值：预增/预减/扭亏/首亏/略增/略减/不变/续亏/续盈
        """
        forecast_type = data.get('forecast_type')
        if forecast_type:
            # 把英文 type 映射为中文（Tushare 可能返回英文）
            type_map = {
                'increase': '预增', 'decrease': '预减',
                'turnaround': '扭亏', 'firstloss': '首亏',
                'slightincrease': '略增', 'slightdecrease': '略减',
                'unchanged': '不变', 'continueloss': '续亏', 'continueprofit': '续盈',
            }
            forecast_type = type_map.get(str(forecast_type).lower(), forecast_type)

        return {
            'has_forecast': bool(data.get('has_forecast', False)),
            'forecast_type': forecast_type,
            'forecast_growth': float(data['forecast_growth']) if data.get('forecast_growth') is not None else None,
            'has_survey': bool(data.get('has_survey', False)),
            'survey_count': int(data.get('survey_count', 0)),
            'has_policy': bool(data.get('has_policy', False)),
        }

    def get_realtime_spot(self, code: str) -> Dict[str, Any]:
        """
        获取单只股票实时行情（使用新浪/腾讯接口）

        Args:
            code: 股票代码，如 '600519'

        Returns:
            dict: {
                'code': '600519',
                'name': '贵州茅台',
                'current': 1443.31,
                'change': -10.65,
                'pct_chg': -0.73,
                'volume': 2521364,
                'amount': 0,
                'high': 1446.5,
                'low': 1433.0,
                'open': 1444.0,
                'close_prev': 1453.96,
                'update_time': '2026-04-13 15:00:01',
                'source': 'sina'
            }
        """
        # 导入放在函数内避免循环导入
        try:
            from realtime_fetcher import get_realtime_fetcher
            fetcher = get_realtime_fetcher()
            return fetcher.get_spot_single(code)
        except Exception as e:
            logger.error(f"获取实时行情失败: {e}")
            return {}

    def get_realtime_batch(self, codes: List[str]) -> pd.DataFrame:
        """
        批量获取实时行情

        Args:
            codes: 股票代码列表

        Returns:
            DataFrame with realtime data for all codes
        """
        try:
            from realtime_fetcher import get_realtime_fetcher
            fetcher = get_realtime_fetcher()
            return fetcher.get_spot(codes)
        except Exception as e:
            logger.error(f"批量获取实时行情失败: {e}")
            return pd.DataFrame()

    def is_market_open(self) -> bool:
        """
        判断当前是否在交易时间

        Returns:
            True if market is open (09:30-11:30, 13:00-15:00 on weekdays)
        """
        try:
            from realtime_fetcher import get_realtime_fetcher
            fetcher = get_realtime_fetcher()
            return fetcher.is_market_open()
        except Exception:
            return False


# 单例
_fetcher_instance = None

def get_fetcher() -> DataFetcher:
    """获取数据获取器单例"""
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = DataFetcher()
    return _fetcher_instance


# ==================== 消息面数据获取器 ====================

class NewsFetcher:
    """
    消息面数据获取器 - AKShare免费接口
    支持：实时新闻、公告、涨跌停原因
    """

    def __init__(self):
        self.api = None
        self._init_api()
        self.cache = DataCache()

    def _init_api(self):
        """初始化AKShare接口"""
        try:
            import akshare as ak
            self.api = ak
        except ImportError:
            logger.warning("AKShare未安装，消息面功能不可用")

    def is_available(self) -> bool:
        return self.api is not None

    def get_general_news(self, limit: int = 50) -> pd.DataFrame:
        """
        获取A股市场快讯

        Returns:
            DataFrame: [关键词, 股票代码, 股票名称, 发布时间, 新闻来源, 新闻内容]
        """
        cache_key = f"news_general_{limit}"
        cached = self.cache.get(cache_key, max_age_minutes=5)  # 新闻5分钟缓存
        if cached is not None and not cached.empty:
            return cached

        if not self.is_available():
            logger.warning("AKShare不可用，无法获取新闻")
            return pd.DataFrame()

        try:
            # stock_news_em 需要传入股票代码，这里用大盘指数演示
            # 返回最新发布的市场/行业新闻
            df = self.api.stock_news_main_cx()
            if df is not None and not df.empty:
                # 统一列名
                rename_map = {
                    '关键词': 'keyword',
                    '股票代码': 'ts_code',
                    '股票名称': 'name',
                    '发布时间': 'pub_time',
                    '新闻来源': 'source',
                    '新闻内容': 'content'
                }
                df = df.rename(columns=rename_map)
                df = df.head(limit)
                self.cache.set(cache_key, df)
                logger.info(f"获取到 {len(df)} 条市场快讯")
                return df
        except Exception as e:
            logger.error(f"获取市场快讯失败: {e}")

        return pd.DataFrame()

    def get_stock_news(self, symbol: str) -> pd.DataFrame:
        """
        获取个股新闻

        Args:
            symbol: 股票代码，如 '000001'

        Returns:
            DataFrame: [关键词, 股票代码, 股票名称, 发布时间, 新闻来源, 新闻内容]
        """
        cache_key = f"news_stock_{symbol}"
        cached = self.cache.get(cache_key, max_age_minutes=10)  # 个股新闻10分钟缓存
        if cached is not None and not cached.empty:
            return cached

        if not self.is_available():
            return pd.DataFrame()

        try:
            # 去除后缀
            symbol = symbol.replace(".sh", "").replace(".sz", "").replace(".SH", "").replace(".SZ", "")
            df = self.api.stock_news_em(symbol=symbol)
            if df is not None and not df.empty:
                rename_map = {
                    '关键词': 'keyword',
                    '股票代码': 'ts_code',
                    '股票名称': 'name',
                    '发布时间': 'pub_time',
                    '新闻来源': 'source',
                    '新闻内容': 'content'
                }
                df = df.rename(columns=rename_map)
                self.cache.set(cache_key, df)
                logger.info(f"获取股票 {symbol} 新闻 {len(df)} 条")
                return df
        except Exception as e:
            logger.error(f"获取个股新闻失败 {symbol}: {e}")

        return pd.DataFrame()

    def get_announcement(self, symbol: str = None, date: str = None, limit: int = 100) -> pd.DataFrame:
        """
        获取个股公告

        Args:
            symbol: 股票代码，如 '000001'，None则获取所有
            date: 日期，格式 YYYYMMDD，默认今日
            limit: 返回条数

        Returns:
            DataFrame: [代码, 名称, 公告类型, 公告时间, 公告标题, 地址]
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        cache_key = f"ann_{symbol}_{date}_{limit}"
        cached = self.cache.get(cache_key, max_age_minutes=30)  # 公告30分钟缓存
        if cached is not None and not cached.empty:
            return cached

        if not self.is_available():
            return pd.DataFrame()

        try:
            if symbol:
                # 个股公告
                symbol = symbol.replace(".sh", "").replace(".sz", "").replace(".SH", "").replace(".SZ", "")
                df = self.api.stock_notice_report(symbol=symbol, date=date)
            else:
                # 获取全市场公告
                df = self.api.stock_notice_report(date=date)

            if df is not None and not df.empty:
                # 统一列名
                rename_map = {
                    '代码': 'ts_code',
                    '名称': 'name',
                    '公告类型': 'ann_type',
                    '公告时间': 'ann_time',
                    '公告标题': 'title',
                    '地址': 'url'
                }
                # 【v9.1】只重命名实际存在的列，新版 AKShare 列名变了也不崩
                existing_cols = {k: v for k, v in rename_map.items() if k in df.columns}
                if existing_cols:
                    df = df.rename(columns=existing_cols)
                df = df.head(limit)
                self.cache.set(cache_key, df)
                logger.info(f"获取公告 {len(df)} 条")
                return df
        except Exception as e:
            # 【v9.1】AKShare 1.18.60 升级后 stock_notice_report 内部会抛 KeyError('代码')
            # 这不影响主流程（外层已捕获），降为 debug 避免日志刷屏
            logger.debug(f"获取公告失败: {e}")

        return pd.DataFrame()

    def get_limit_up_reason(self, trade_date: str = None) -> pd.DataFrame:
        """
        获取涨停原因

        Args:
            trade_date: 交易日期，格式 YYYYMMDD，默认今日

        Returns:
            DataFrame: [序号, 代码, 名称, 涨停时间, 涨停封板时间, 涨停统计, 涨停原因, 流通市值, 预测明天]
        """
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y%m%d")

        cache_key = f"limit_up_{trade_date}"
        cached = self.cache.get(cache_key, max_age_minutes=15)  # 涨停原因15分钟缓存
        if cached is not None and not cached.empty:
            return cached

        if not self.is_available():
            return pd.DataFrame()

        try:
            df = self.api.stock_tfp_em(date=trade_date)
            if df is not None and not df.empty:
                # 统一列名 - 基于实际API返回的列名
                rename_map = {
                    '序号': 'seq',
                    '代码': 'ts_code',
                    '名称': 'name',
                    '涨停时间': 'limit_time',
                    '涨停封板时间': 'seal_time',
                    '涨停统计': 'limit_stat',
                    '涨停原因': 'reason',
                    '流通市值': 'mkt_cap',
                    '预测明天': 'predict'
                }
                df = df.rename(columns=rename_map)
                self.cache.set(cache_key, df)
                logger.info(f"获取涨停股票 {len(df)} 只")
                return df
        except Exception as e:
            logger.error(f"获取涨停原因失败: {e}")

        return pd.DataFrame()

    def get_limit_down_reason(self, trade_date: str = None) -> pd.DataFrame:
        """
        获取跌停原因

        Args:
            trade_date: 交易日期，格式 YYYYMMDD，默认今日

        Returns:
            DataFrame: 同涨停原因
        """
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y%m%d")

        cache_key = f"limit_down_{trade_date}"
        cached = self.cache.get(cache_key, max_age_minutes=15)
        if cached is not None and not cached.empty:
            return cached

        if not self.is_available():
            return pd.DataFrame()

        try:
            df = self.api.stock_tfp_em(date=trade_date, statue="down")
            if df is not None and not df.empty:
                rename_map = {
                    '序号': 'seq',
                    '代码': 'ts_code',
                    '名称': 'name',
                    '涨停时间': 'limit_time',
                    '涨停封板时间': 'seal_time',
                    '涨停统计': 'limit_stat',
                    '涨停原因': 'reason',
                    '流通市值': 'mkt_cap',
                    '预测明天': 'predict'
                }
                df = df.rename(columns=rename_map)
                self.cache.set(cache_key, df)
                logger.info(f"获取跌停股票 {len(df)} 只")
                return df
        except Exception as e:
            logger.error(f"获取跌停原因失败: {e}")

        return pd.DataFrame()

    def get_hot_stocks(self, limit: int = 50) -> pd.DataFrame:
        """
        获取热门股票

        Args:
            limit: 返回条数

        Returns:
            DataFrame: [股票代码, 股票名称, 涨跌幅, 热度排名, 原因]
        """
        cache_key = f"hot_stocks_{limit}"
        cached = self.cache.get(cache_key, max_age_minutes=5)
        if cached is not None and not cached.empty:
            return cached

        if not self.is_available():
            return pd.DataFrame()

        try:
            df = self.api.stock_hot_up_em()
            if df is not None and not df.empty:
                df = df.head(limit)
                self.cache.set(cache_key, df)
                logger.info(f"获取热门股票 {len(df)} 只")
                return df
        except Exception as e:
            logger.error(f"获取热门股票失败: {e}")

        return pd.DataFrame()

    def analyze_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        分析个股消息面情绪

        Args:
            symbol: 股票代码

        Returns:
            dict: {
                'score': 情绪评分 0-100,
                'signal': '利好'/'利空'/'中性',
                'news_count': 新闻数量,
                'ann_count': 公告数量,
                'limit_up': 是否涨停,
                'keywords': [利好关键词列表],
                'risk_keywords': [风险关键词列表],
                'summary': '综合摘要'
            }
        """
        result = {
            'score': 50,  # 基础分
            'signal': '中性',
            'news_count': 0,
            'ann_count': 0,
            'limit_up': False,
            'keywords': [],
            'risk_keywords': [],
            'summary': ''
        }

        # 利好/利空关键词
        positive_keywords = ['业绩预增', '大幅增长', '订单', '合作', '突破', '中标', '研发',
                           '产能扩张', '市场份额', '政策支持', '战略', '增持', '回购', '转型']
        negative_keywords = ['业绩预减', '大幅下降', '亏损', '减持', '诉讼', '监管', '问询',
                            '风险提示', '终止', '违规', '减持', '商誉减值', '应收账款']

        # 1. 获取个股新闻
        news_df = self.get_stock_news(symbol)
        if news_df is not None and not news_df.empty:
            result['news_count'] = len(news_df)
            # 关键词统计
            all_content = ' '.join(news_df.get('content', '').astype(str).tolist())
            for kw in positive_keywords:
                if kw in all_content:
                    result['keywords'].append(kw)
                    result['score'] += 5
            for kw in negative_keywords:
                if kw in all_content:
                    result['risk_keywords'].append(kw)
                    result['score'] -= 8

        # 2. 获取公告
        try:
            ann_df = self.get_announcement(symbol=symbol)
            if ann_df is not None and not ann_df.empty:
                result['ann_count'] = len(ann_df)
                # 检查公告标题
                titles = ' '.join(ann_df.get('title', ann_df.get('ann_type', '')).astype(str).tolist())
                for kw in positive_keywords:
                    if kw in titles:
                        result['keywords'].append(f"[公告]{kw}")
                        result['score'] += 8  # 公告权重更高
                for kw in negative_keywords:
                    if kw in titles:
                        result['risk_keywords'].append(f"[公告]{kw}")
                        result['score'] -= 12
        except Exception as e:
            logger.debug(f"获取公告失败: {e}")

        # 3. 检查是否涨停
        today = datetime.now().strftime("%Y%m%d")
        limit_df = self.get_limit_up_reason(trade_date=today)
        if limit_df is not None and not limit_df.empty:
            symbol_clean = symbol.replace(".sh", "").replace(".sz", "").replace(".SH", "").replace(".SZ", "")
            for _, row in limit_df.iterrows():
                code = str(row.get('ts_code', '')).replace(".sh", "").replace(".sz", "").replace(".SH", "").replace(".SZ", "")
                if symbol_clean in code:
                    result['limit_up'] = True
                    result['score'] += 20
                    result['keywords'].append(f"涨停({row.get('reason', '')})")
                    break

        # 限制分数范围
        result['score'] = max(0, min(100, result['score']))

        # 判断信号
        if result['score'] >= 65:
            result['signal'] = '利好'
        elif result['score'] <= 35:
            result['signal'] = '利空'
        else:
            result['signal'] = '中性'

        # 生成摘要
        if result['keywords'] or result['risk_keywords']:
            result['summary'] = f"发现 {len(result['keywords'])} 个利好因素, {len(result['risk_keywords'])} 个风险因素"
        else:
            result['summary'] = "无明显利好/利空信号"

        return result


# 单例
_news_fetcher_instance = None

def get_news_fetcher() -> NewsFetcher:
    """获取消息面数据获取器单例"""
    global _news_fetcher_instance
    if _news_fetcher_instance is None:
        _news_fetcher_instance = NewsFetcher()
    return _news_fetcher_instance
