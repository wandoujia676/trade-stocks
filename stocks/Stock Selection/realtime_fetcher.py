"""
实时行情获取器 - 小金库5.0核心组件
使用新浪/腾讯接口获取盘中实时行情
无需代理，不依赖东财
"""
import re
import time
import logging
from datetime import datetime, time as dtime
from typing import List, Dict, Any, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class RealtimeFetcher:
    """
    实时行情获取器

    数据源优先级:
    1. 新浪 (hq.sinajs.cn) - 优先
    2. 腾讯 (qt.gtimg.cn) - 备选

    特点:
    - 无需代理，直接访问
    - 支持批量获取（新浪最多可一次请求约100只）
    - 返回实时价格、涨跌幅、成交量、成交额等
    """

    # 新浪实时数据字段
    SINA_FIELDS = [
        'name',           # 0  名称
        'open',           # 1  开盘价
        'close_prev',     # 2  昨收
        'current',        # 3  当前价
        'high',           # 4  最高
        'low',            # 5  最低
        'bid',            # 6  买价
        'ask',            # 7  卖价
        'volume',         # 8  成交量(股)
        'amount',         # 9  成交额(元)
        'b1_v',           # 10 买1量
        'b1_p',           # 11 买1价
        'b2_v',           # 12 买2量
        'b2_p',           # 13 买2价
        'b3_v',           # 14 买3量
        'b3_p',           # 15 买3价
        'b4_v',           # 16 买4量
        'b4_p',           # 17 买4价
        'b5_v',           # 18 买5量
        'b5_p',           # 19 买5价
        'date',           # 20 日期
        'time',           # 21 时间
    ]

    # 腾讯实时数据字段(~分隔)
    TENCENT_FIELDS = [
        'name',           # 0  名称
        'code',           # 1  代码
        'current',        # 2  当前价
        'close_prev',     # 3  昨收
        'open',           # 4  开盘价
        'volume',         # 5  成交量(手)
        'b1_p',           # 6  买1价
        'b1_v',           # 7  买1量
        'b2_p',           # 8  买2价
        'b2_v',           # 9  买2量
        'b3_p',           # 10 买3价
        'b3_v',           # 11 买3量
        'b4_p',           # 12 买4价
        'b4_v',           # 13 买4量
        'b5_p',           # 14 买5价
        'b5_v',           # 15 买5量
        'date',           # 16 日期
        'time',           # 17 时间
        'unused',         # 18 (无用)
        'change',         # 19 涨跌
        'pct_chg',       # 20 涨跌幅(%)
        'high',           # 21 最高
        'low',            # 22 最低
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False  # 忽略系统代理
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn',
        })
        self._last_request_time = 0
        self._min_request_interval = 0.5  # 最小请求间隔(秒)

    def _rate_limit(self):
        """频率限制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def is_market_open(self) -> bool:
        """判断当前是否在交易时间"""
        now = datetime.now()
        current_time = now.time()

        # 周末休市
        if now.weekday() >= 5:
            return False

        # 交易时间: 09:30-11:30, 13:00-15:00
        morning_start = dtime(9, 30)
        morning_end = dtime(11, 30)
        afternoon_start = dtime(13, 0)
        afternoon_end = dtime(15, 0)

        if morning_start <= current_time <= morning_end:
            return True
        if afternoon_start <= current_time <= afternoon_end:
            return True

        return False

    def get_spot_sina(self, codes: List[str]) -> pd.DataFrame:
        """
        通过新浪接口获取实时行情（批量）

        Args:
            codes: 股票代码列表，如 ['600519', '000001'] 或 ['sh600519', 'sz000001']

        Returns:
            DataFrame with columns: code, name, current, change, pct_chg, volume, amount, high, low, open, close_prev
        """
        if not codes:
            return pd.DataFrame()

        # 格式化代码（确保有sh/sz前缀）
        formatted = []
        for code in codes:
            code = code.strip().replace('.SH', '').replace('.SZ', '')
            if code.startswith(('6', '5')):
                formatted.append(f'sh{code}')
            elif code.startswith(('0', '1', '3')):
                formatted.append(f'sz{code}')
            else:
                formatted.append(f'sh{code}')  # 默认上交所

        # 构建请求URL（每100只分一批）
        results = []
        batch_size = 100

        for i in range(0, len(formatted), batch_size):
            batch = formatted[i:i+batch_size]
            url = f'https://hq.sinajs.cn/list={",".join(batch)}'

            try:
                self._rate_limit()
                resp = self.session.get(url, timeout=10)
                resp.encoding = 'gbk'

                # 解析返回数据
                for line in resp.text.split('\n'):
                    if '="' not in line:
                        continue

                    # 提取代码和数据
                    match = re.search(r'hq_str_(\w+)="([^"]*)"', line)
                    if not match:
                        continue

                    code_raw = match.group(1)  # 如 sh600519
                    data_str = match.group(2)

                    if not data_str or data_str.count(',') < 10:
                        continue

                    parts = data_str.split(',')

                    try:
                        # 转换代码格式
                        code = code_raw.replace('sh', '').replace('sz', '')

                        # 计算涨跌和涨跌幅
                        current = float(parts[3]) if parts[3] else 0
                        close_prev = float(parts[2]) if parts[2] else 0
                        change = current - close_prev
                        pct_chg = (change / close_prev * 100) if close_prev else 0

                        # 成交量转换为万手
                        volume = int(parts[8]) if parts[8] else 0
                        amount = float(parts[9]) if parts[9] else 0

                        results.append({
                            'code': code,
                            'name': parts[0],
                            'current': current,
                            'change': round(change, 2),
                            'pct_chg': round(pct_chg, 2),
                            'volume': volume,
                            'amount': amount,
                            'high': float(parts[4]) if parts[4] else 0,
                            'low': float(parts[5]) if parts[5] else 0,
                            'open': float(parts[1]) if parts[1] else 0,
                            'close_prev': close_prev,
                            'bid': float(parts[6]) if parts[6] else 0,
                            'ask': float(parts[7]) if parts[7] else 0,
                            'update_time': f"{parts[30]} {parts[31]}" if len(parts) > 31 else '',
                            'source': 'sina',
                        })
                    except (ValueError, IndexError) as e:
                        logger.debug(f'解析失败 {code_raw}: {e}')
                        continue

            except Exception as e:
                logger.error(f'新浪请求失败: {e}')

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df['code'] = df['code'].astype(str).str.zfill(6)
        return df

    def get_spot_tencent(self, codes: List[str]) -> pd.DataFrame:
        """
        通过腾讯接口获取实时行情（批量）

        Args:
            codes: 股票代码列表

        Returns:
            DataFrame with same format as get_spot_sina
        """
        if not codes:
            return pd.DataFrame()

        # 格式化代码
        formatted = []
        for code in codes:
            code = code.strip().replace('.SH', '').replace('.SZ', '')
            if code.startswith(('6', '5')):
                formatted.append(f'sh{code}')
            elif code.startswith(('0', '1', '3')):
                formatted.append(f'sz{code}')
            else:
                formatted.append(f'sh{code}')

        # 构建请求URL
        results = []
        batch_size = 100

        for i in range(0, len(formatted), batch_size):
            batch = formatted[i:i+batch_size]
            url = f'https://qt.gtimg.cn/q={",".join(batch)}'

            try:
                self._rate_limit()
                resp = self.session.get(url, timeout=10)
                resp.encoding = 'gbk'

                for line in resp.text.split('\n'):
                    if '="' not in line:
                        continue

                    match = re.search(r'v_(\w+)="([^"]*)"', line)
                    if not match:
                        continue

                    code_raw = match.group(1)
                    data_str = match.group(2)

                    if not data_str:
                        continue

                    parts = data_str.split('~')
                    if len(parts) < 23:
                        continue

                    try:
                        code = code_raw.replace('sh', '').replace('sz', '')

                        current = float(parts[2]) if parts[2] else 0
                        close_prev = float(parts[3]) if parts[3] else 0
                        change = float(parts[19]) if parts[19] else 0
                        pct_chg = float(parts[20]) if parts[20] else 0
                        volume = int(parts[6]) * 100 if parts[6] else 0  # 转换为股

                        results.append({
                            'code': code,
                            'name': parts[1],
                            'current': current,
                            'change': round(change, 2),
                            'pct_chg': round(pct_chg, 2),
                            'volume': volume,
                            'amount': 0,  # 腾讯接口不返回成交额
                            'high': float(parts[21]) if parts[21] else 0,
                            'low': float(parts[22]) if parts[22] else 0,
                            'open': float(parts[4]) if parts[4] else 0,
                            'close_prev': close_prev,
                            'bid': float(parts[6]) if parts[6] else 0,
                            'ask': 0,
                            'update_time': f"{parts[16]} {parts[17]}" if len(parts) > 17 else '',
                            'source': 'tencent',
                        })
                    except (ValueError, IndexError) as e:
                        logger.debug(f'解析失败 {code_raw}: {e}')
                        continue

            except Exception as e:
                logger.error(f'腾讯请求失败: {e}')

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df['code'] = df['code'].astype(str).str.zfill(6)
        return df

    def get_spot(self, codes: List[str]) -> pd.DataFrame:
        """
        获取实时行情（自动降级）

        优先使用新浪接口，失败后尝试腾讯

        Args:
            codes: 股票代码列表

        Returns:
            DataFrame with realtime market data
        """
        if not codes:
            return pd.DataFrame()

        # 优先使用新浪
        df = self.get_spot_sina(codes)
        if df is not None and not df.empty:
            return df

        # 降级到腾讯
        logger.warning('新浪接口失败，降级到腾讯')
        df = self.get_spot_tencent(codes)
        return df

    def get_spot_single(self, code: str) -> Optional[Dict[str, Any]]:
        """
        获取单只股票实时行情

        Args:
            code: 股票代码，如 '600519'

        Returns:
            dict with realtime data, or None if failed
        """
        df = self.get_spot([code])
        if df is not None and not df.empty:
            return df.iloc[0].to_dict()
        return None


# 单例
_fetcher_instance = None

def get_realtime_fetcher() -> RealtimeFetcher:
    """获取实时行情获取器单例"""
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = RealtimeFetcher()
    return _fetcher_instance


if __name__ == '__main__':
    # 测试
    print('=== 测试实时行情获取 ===')

    fetcher = RealtimeFetcher()

    # 测试是否在交易时间
    print(f'市场开盘状态: {fetcher.is_market_open()}')

    # 测试单股
    print('\n[单股测试] 贵州茅台 600519')
    result = fetcher.get_spot_single('600519')
    if result:
        print(f"名称: {result['name']}")
        print(f"现价: {result['current']}")
        print(f"涨跌: {result['change']} ({result['pct_chg']}%)")
        print(f"最高: {result['high']}")
        print(f"最低: {result['low']}")
        print(f"成交量: {result['volume']}")
        print(f"更新时间: {result['update_time']}")
    else:
        print('获取失败')

    # 测试批量
    print('\n[批量测试] 多只股票')
    codes = ['600519', '000001', '300750', '002594', '600036']
    df = fetcher.get_spot(codes)
    if df is not None and not df.empty:
        print(df[['code', 'name', 'current', 'pct_chg']].to_string(index=False))
    else:
        print('获取失败')
