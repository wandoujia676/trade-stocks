"""
卖出信号检测模块 - 整合9本实战书籍的卖出经验
基于《一买即涨》《交易真相》《股道人生》《量学》《短线操盘》等

卖出信号类型：
1. 高位十字星（长上下影线）
2. 高位长上影线（>5%）
3. 高位大阴线（>5%）
4. 均线死叉（5日死叉10日）
5. MACD死叉
6. 缩量滞涨
7. 跌破20日均线
8. 量价背离
"""

import logging
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SellSignals:
    """
    卖出信号检测器

    基于九本书的卖出理论：
    - 《一买即涨》：高位十字星、长上影、长下影、大阴线、分时图均价线拐头
    - 《交易真相》：截断亏损让利润奔跑、止损不该被动等待
    - 《股道人生》：买在分歧卖在一致、止损7-8%
    - 《量学》：高量柱后缩量滞涨、量价背离
    - 《短线操盘》：早晨之星卖出、跌破均线
    """

    def __init__(self):
        pass

    def detect_all_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测所有卖出信号

        Returns:
            {
                "signals": [{"type": "高位十字星", "weight": 20, "source": "《一买即涨》"}, ...],
                "total_score": 75,
                "signal_count": 3,
                "details": {...}
            }
        """
        if df is None or len(df) < 20:
            return {"error": "数据不足", "signals": [], "total_score": 0, "signal_count": 0}

        result = {
            "signals": [],
            "total_score": 0,
            "signal_count": 0,
            "details": {}
        }

        # 检测各类信号
        signals_found = []

        # 1. 高位十字星
        cross_star = self._check_cross_star(df)
        if cross_star["detected"]:
            signals_found.append(cross_star)

        # 2. 高位长上影线
        upper_shadow = self._check_upper_shadow(df)
        if upper_shadow["detected"]:
            signals_found.append(upper_shadow)

        # 3. 高位大阴线
        big_negative = self._check_big_negative(df)
        if big_negative["detected"]:
            signals_found.append(big_negative)

        # 4. 均线死叉
        ma_death_cross = self._check_ma_death_cross(df)
        if ma_death_cross["detected"]:
            signals_found.append(ma_death_cross)

        # 5. MACD死叉
        macd_death_cross = self._check_macd_death_cross(df)
        if macd_death_cross["detected"]:
            signals_found.append(macd_death_cross)

        # 6. 缩量滞涨
        volume_price_divergence = self._check_volume_price_divergence(df)
        if volume_price_divergence["detected"]:
            signals_found.append(volume_price_divergence)

        # 7. 跌破20日均线
        break_ma20 = self._check_break_ma20(df)
        if break_ma20["detected"]:
            signals_found.append(break_ma20)

        # 8. 量价背离
        vol_price_break = self._check_vol_price_break(df)
        if vol_price_break["detected"]:
            signals_found.append(vol_price_break)

        result["signals"] = signals_found
        result["signal_count"] = len(signals_found)
        result["total_score"] = sum(s["weight"] for s in signals_found)
        result["details"] = self._collect_details(df, signals_found)

        return result

    def _check_cross_star(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测高位十字星（《一买即涨》）
        特征：实体很小，上下影线较长，出现在相对高位
        """
        result = {"detected": False, "type": "高位十字星", "weight": 20,
                  "source": "《一买即涨》", "desc": ""}

        if len(df) < 5:
            return result

        closes = df['close'].astype(float).values
        opens = df['open'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values

        # 取最近3根K线
        for i in range(-3, 0):
            idx = len(closes) + i
            if idx < 0:
                continue

            o, c, h, l = opens[idx], closes[idx], highs[idx], lows[idx]
            body = abs(c - o)
            upper_shadow = h - max(o, c)
            lower_shadow = min(o, c) - l
            full_range = h - l

            if full_range == 0:
                continue

            # 判断是否为十字星：实体小于整根K线的10%，上下影线明显
            body_ratio = body / full_range if full_range > 0 else 0
            upper_ratio = upper_shadow / full_range if full_range > 0 else 0
            lower_ratio = lower_shadow / full_range if full_range > 0 else 0

            # 十字星特征：实体小，上下影线各占一定比例
            is_cross_star = (body_ratio < 0.1 and
                           upper_ratio > 0.2 and
                           lower_ratio > 0.2)

            if is_cross_star:
                # 检查是否在相对高位（接近20日新高）
                recent_high = max(highs[-20:])
                if h > recent_high * 0.95:
                    result["detected"] = True
                    result["desc"] = f"第{abs(i)}天：十字星出现在高位，上影{upper_ratio*100:.0f}%，下影{lower_ratio*100:.0f}%"
                    break

        return result

    def _check_upper_shadow(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测高位长上影线（《一买即涨》）
        特征：上影线长度大于实体2倍以上，实体跌幅>2%
        """
        result = {"detected": False, "type": "高位长上影线", "weight": 15,
                  "source": "《一买即涨》", "desc": ""}

        if len(df) < 5:
            return result

        closes = df['close'].astype(float).values
        opens = df['open'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values

        # 取最近2根K线
        for i in range(-2, 0):
            idx = len(closes) + i
            if idx < 0:
                continue

            o, c, h, l = float(opens[idx]), float(closes[idx]), float(highs[idx]), float(lows[idx])
            body = abs(c - o)
            upper_shadow = h - max(o, c)
            full_range = h - l

            if full_range == 0:
                continue

            # 长上影线特征：上影线大于实体2倍，且价格下跌
            price_drop = (c - o) < 0  # 收阴线
            shadow_vs_body = upper_shadow > body * 2 if body > 0 else False
            shadow_ratio = upper_shadow / full_range

            if price_drop and shadow_vs_body and shadow_ratio > 0.5:
                # 检查是否在相对高位
                recent_high = max(highs[-20:])
                if h > recent_high * 0.92:
                    result["detected"] = True
                    result["desc"] = f"第{abs(i)}天：上影线长度{upper_shadow:.2f}元，占K线{shadow_ratio*100:.0f}%，冲高回落"
                    break

        return result

    def _check_big_negative(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测高位大阴线（《一买即涨》）
        特征：高开低走，实体大于5%，伴随成交量放大
        """
        result = {"detected": False, "type": "高位大阴线", "weight": 15,
                  "source": "《一买即涨》", "desc": ""}

        if len(df) < 5:
            return result

        closes = df['close'].astype(float).values
        opens = df['open'].astype(float).values
        highs = df['high'].astype(float).values
        volumes = df['volume'].astype(float).values

        # 最新K线
        o, c = float(opens[-1]), float(closes[-1])
        h = float(highs[-1])
        body_pct = (c - o) / o * 100 if o > 0 else 0

        # 大阴线特征：高开低走，实体>5%
        is_big_negative = (o > c and body_pct < -5)

        if is_big_negative:
            # 检查是否在相对高位
            recent_high = max(highs[-20:])
            recent_vol_avg = np.mean(volumes[-20:])

            if h > recent_high * 0.90:
                vol_ratio = volumes[-1] / recent_vol_avg if recent_vol_avg > 0 else 1
                result["detected"] = True
                result["desc"] = f"今日跌幅{body_pct:.1f}%，成交量放大{vol_ratio:.1f}倍，主力出货嫌疑"
            elif vol_ratio > 1.5:
                # 不在高位但放量下跌
                result["detected"] = True
                result["desc"] = f"今日跌幅{body_pct:.1f}%，成交量放大{vol_ratio:.1f}倍，注意风险"

        return result

    def _check_ma_death_cross(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测均线死叉（《一买即涨》- 5线死叉10线）
        """
        result = {"detected": False, "type": "均线死叉", "weight": 15,
                  "source": "《一买即涨》", "desc": ""}

        if len(df) < 15:
            return result

        closes = df['close'].astype(float).values

        # 计算均线
        ma5_current = np.mean(closes[-5:])
        ma10_current = np.mean(closes[-10:])

        ma5_prev = np.mean(closes[-6:-1])
        ma10_prev = np.mean(closes[-11:-6])

        # 死叉：MA5从上穿变为下穿MA10
        if ma5_prev > ma10_prev and ma5_current < ma10_current:
            result["detected"] = True
            result["desc"] = f"MA5({ma5_current:.2f})下穿MA10({ma10_current:.2f})，短期趋势转弱"

        return result

    def _check_macd_death_cross(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测MACD死叉（《一买即涨》《都市》）
        """
        result = {"detected": False, "type": "MACD死叉", "weight": 15,
                  "source": "《一买即涨》《都市》", "desc": ""}

        if len(df) < 35:
            return result

        closes = df['close'].astype(float).values

        # 计算MACD
        macd, signal, hist = self._calc_macd(closes)

        if len(macd) < 2:
            return result

        macd_val = float(macd[-1])
        signal_val = float(signal[-1])
        macd_prev = float(macd[-2])
        signal_prev = float(signal[-2])

        # 死叉：DIF从上穿变为下穿signal线
        if macd_prev > signal_prev and macd_val < signal_val:
            result["detected"] = True
            result["desc"] = f"DIF({macd_val:.3f})下穿DEA({signal_val:.3f})，动量减弱"

        return result

    def _check_volume_price_divergence(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测缩量滞涨（《量学》- 高量柱后缩量滞涨）
        特征：前期放量上涨，近期缩量但价格不创新高
        """
        result = {"detected": False, "type": "缩量滞涨", "weight": 10,
                  "source": "《量学》", "desc": ""}

        if len(df) < 20:
            return result

        closes = df['close'].astype(float).values
        volumes = df['volume'].astype(float).values

        # 近期5日均量 vs 前期20日均量
        vol_5avg = np.mean(volumes[-5:])
        vol_20avg = np.mean(volumes[-20:])

        # 近期价格 vs 前期高点
        price_5avg = np.mean(closes[-5:])
        price_high_20 = max(closes[-20:])

        # 缩量（量能萎缩到60%以下）但价格未创新高
        vol_ratio = vol_5avg / vol_20avg if vol_20avg > 0 else 1
        price_ratio = price_5avg / price_high_20 if price_high_20 > 0 else 1

        if vol_ratio < 0.6 and price_ratio < 0.95:
            result["detected"] = True
            result["desc"] = f"量能萎缩至前期{vol_ratio*100:.0f}%，价格仅高位{price_ratio*100:.0f}%，滞涨明显"

        return result

    def _check_break_ma20(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测跌破20日均线（《短线操盘》）
        """
        result = {"detected": False, "type": "跌破20日均线", "weight": 10,
                  "source": "《短线操盘》", "desc": ""}

        if len(df) < 25:
            return result

        closes = df['close'].astype(float).values
        closes_prev = df['close'].astype(float).values

        ma20 = np.mean(closes[-20:])

        current_price = closes[-1]
        prev_price = closes[-2] if len(closes) > 1 else current_price

        # 今日跌破但昨日在均线上方
        if current_price < ma20 and prev_price > ma20:
            drop_pct = (ma20 - current_price) / ma20 * 100
            result["detected"] = True
            result["desc"] = f"股价跌破MA20({ma20:.2f})，跌幅{ drop_pct:.1f}%，趋势转弱"

        return result

    def _check_vol_price_break(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测量价背离（《量学》- 量为价先的逆运用）
        特征：价格创新高但成交量萎缩
        """
        result = {"detected": False, "type": "量价背离", "weight": 10,
                  "source": "《量学》", "desc": ""}

        if len(df) < 20:
            return result

        closes = df['close'].astype(float).values
        volumes = df['volume'].astype(float).values

        # 价格创20日新高
        current_price = closes[-1]
        high_20 = max(closes[-20:-1])  # 排除今天

        # 今日量能 vs 5日均量
        vol_today = volumes[-1]
        vol_5avg = np.mean(volumes[-6:-1])

        if current_price > high_20 and vol_today < vol_5avg * 0.8:
            result["detected"] = True
            result["desc"] = f"价格创新高({current_price:.2f})但量能萎缩至5日均量{vol_today/vol_5avg*100:.0f}%，量价背离"

        return result

    def _collect_details(self, df: pd.DataFrame, signals: List[Dict]) -> Dict[str, Any]:
        """收集详细信息"""
        details = {}

        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        volumes = df['volume'].astype(float).values

        # 基本信息
        details["当前价格"] = round(closes[-1], 2)
        details["20日高价"] = round(max(highs[-20:]), 2)
        details["20日低价"] = round(min(df['low'].astype(float).values[-20:]), 2)
        details["量比"] = round(volumes[-1] / np.mean(volumes[-6:-1]), 2) if len(volumes) > 5 else 1

        # 计算均线
        details["MA5"] = round(np.mean(closes[-5:]), 2)
        details["MA10"] = round(np.mean(closes[-10:]), 2)
        details["MA20"] = round(np.mean(closes[-20:]), 2)

        # MACD
        macd, signal, hist = self._calc_macd(closes)
        details["DIF"] = round(float(macd[-1]), 3) if len(macd) > 0 else 0
        details["DEA"] = round(float(signal[-1]), 3) if len(signal) > 0 else 0
        details["MACD柱"] = round(float(hist[-1]), 3) if len(hist) > 0 else 0

        return details

    def _calc_macd(self, prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算MACD"""
        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)
        macd = ema_fast - ema_slow
        signal_line = self._ema(macd, signal)
        histogram = macd - signal_line
        return macd, signal_line, histogram

    def _ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """计算EMA"""
        alpha = 2 / (period + 1)
        ema = np.zeros_like(prices, dtype=float)
        ema[0] = prices[0]
        for i in range(1, len(prices)):
            ema[i] = alpha * prices[i] + (1 - alpha) * ema[i-1]
        return ema


# 单例
_sell_signals_instance = None

def get_sell_signals() -> SellSignals:
    """获取卖出信号检测器单例"""
    global _sell_signals_instance
    if _sell_signals_instance is None:
        _sell_signals_instance = SellSignals()
    return _sell_signals_instance
