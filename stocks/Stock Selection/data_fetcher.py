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

    def get(self, key: str, max_age_minutes: int = 60) -> Optional[pd.DataFrame]:
        """获取缓存数据，如果过期返回None"""
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

            return pd.read_json(io.StringIO(data_json))

    def set(self, key: str, df: pd.DataFrame):
        """设置缓存"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO data_cache (key, data, updated_at) VALUES (?, ?, ?)",
                (key, df.to_json(), datetime.now().isoformat())
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

    def is_available(self) -> bool:
        return self.api is not None

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

    def get_daily(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取日线数据"""
        if not self.is_available():
            raise DataSourceError("AKShare不可用")

        try:
            symbol = self._convert_code(symbol)
            period = "daily"
            if start_date and end_date:
                start = datetime.strptime(start_date, "%Y%m%d")
                end = datetime.strptime(end_date, "%Y%m%d")
                days = (end - start).days
                if days <= 100:
                    period = "daily"
                elif days <= 300:
                    period = "weekly"
                else:
                    period = "monthly"

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

    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """获取股票基本信息"""
        if not self.is_available():
            raise DataSourceError("AKShare不可用")

        try:
            symbol = self._convert_code(symbol)
            df = self.api.stock_individual_info_em(symbol=symbol.split(".")[0])
            info = dict(zip(df['item'], df['value']))
            return info
        except Exception as e:
            logger.error(f"AKShare info失败: {e}")
            raise DataSourceError(f"AKShare API错误: {e}")

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
        self.fetchers = {
            "tushare": TushareFetcher(),
            "akshare": AKShareFetcher(),
            "baostock": BaostockFetcher(),
        }
        self.current_source = None
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

        # 尝试各数据源
        errors = []
        for source_name in DATA_SOURCE_PRIORITY:
            fetcher = self.fetchers.get(source_name)
            if not fetcher or not fetcher.is_available():
                continue

            try:
                if source_name == "tushare":
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

            except DataSourceError as e:
                errors.append(f"{source_name}: {e}")
                continue

        raise DataSourceError(f"所有数据源均失败: {errors}")

    def get_realtime(self, symbol: str) -> Dict[str, Any]:
        """
        获取实时行情（单股）
        返回关键字段的字典
        """
        symbol = symbol.strip()

        # 先尝试Tushare（如果有今日数据）
        try:
            if self.fetchers["tushare"] and self.fetchers["tushare"].is_available():
                # Tushare的daily可以获取最近交易日的数据
                ts_code = self._to_tushare_code(symbol)
                df = self.fetchers["tushare"].get_daily(ts_code=ts_code)
                if df is not None and not df.empty:
                    latest = df.iloc[0]  # 最新一条是最新交易日的
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

    def get_realtime_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        批量获取实时行情
        返回 {代码: 行情字典}
        """
        results = {}

        # 批量获取日线数据（每批最多200只）
        batch_size = 200
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            try:
                # 转换代码格式
                ts_codes = [self._to_tushare_code(s) for s in batch]
                # 使用Tushare的daily批量接口
                if self.fetchers["tushare"] and self.fetchers["tushare"].is_available():
                    import tushare as ts
                    pro = ts.pro_api(self.token)
                    # 限制频率
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
            }
            df = df.rename(columns=rename_map)

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
