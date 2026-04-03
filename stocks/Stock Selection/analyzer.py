"""
综合分析引擎 - 多维度股票分析
整合技术面、基本面、消息面分析
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

from config import ANALYZER_DEFAULTS, KLINE_PATTERNS
from data_fetcher import get_fetcher
from warfare import get_warfare

logger = logging.getLogger(__name__)


class StockAnalyzer:
    """
    股票综合分析器

    分析维度：
    - 技术面：K线形态、均线、MACD/BOLL/KDJ、量价关系
    - 基本面：财务指标、行业地位
    - 消息面：公告、新闻情绪
    - 综合信号：买入/持有/卖出建议
    """

    def __init__(self, params: Dict[str, Any] = None):
        self.params = {**ANALYZER_DEFAULTS, **(params or {})}
        self.fetcher = get_fetcher()
        self.warfare = get_warfare()

    def analyze(self, symbol: str) -> Dict[str, Any]:
        """
        执行综合分析

        Args:
            symbol: 股票代码，如 "000001" 或 "000001.sz"

        Returns:
            结构化分析报告
        """
        logger.info(f"开始分析: {symbol}")

        symbol = symbol.strip().replace(".sz", "").replace(".sh", "")

        # 获取数据
        df = self.fetcher.get_daily(symbol)
        if df is None or len(df) < 60:
            return {"error": f"数据不足，无法分析 {symbol}"}

        # 基本信息
        info = self._get_basic_info(symbol)

        # 综合战法评估（整合9本书经验）
        warfare_result = self.warfare.evaluate(df, info)

        # 技术面分析（保留原版作为参考）
        tech_analysis = self._analyze_technical(df)

        # K线形态识别
        patterns = self._identify_patterns(df)

        # 基本面分析（简化）
        fund_analysis = self._analyze_fundamental(symbol)

        # 综合信号（使用战法结果）
        signal = self._generate_signal_from_warfare(warfare_result)

        # 构建报告
        report = {
            "股票代码": symbol,
            "股票名称": info.get("name", info.get("股票名称", "未知")),
            "分析时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "最新价格": float(df['close'].iloc[-1]) if 'close' in df.columns else 0,
            "涨跌幅": float(df['pct_change'].iloc[-1]) if 'pct_change' in df.columns else 0,

            "战法评估": warfare_result,  # 综合战法结果
            "技术面": tech_analysis,
            "K线形态": patterns,
            "基本面": fund_analysis,
            "综合信号": signal,
        }

        return report

    def _get_basic_info(self, symbol: str) -> Dict[str, Any]:
        """获取基本信息"""
        try:
            info = self.fetcher.get_stock_info(symbol)
            if info:
                return {
                    "name": info.get("股票简称", info.get("名称", "")),
                    "行业": info.get("行业", ""),
                    "市值": info.get("总市值", ""),
                    "流通市值": info.get("流通市值", ""),
                }
        except Exception as e:
            logger.debug(f"获取基本信息失败: {e}")

        # 尝试从实时数据获取
        try:
            realtime = self.fetcher.get_realtime(symbol)
            if realtime:
                return {
                    "name": realtime.get("name", ""),
                    "行业": "",
                    "市值": "",
                }
        except:
            pass

        return {"name": "未知", "行业": "", "市值": ""}

    def _analyze_technical(self, df: pd.DataFrame) -> Dict[str, Any]:
        """技术面分析"""
        tech = {}

        try:
            closes = df['close'].astype(float).values
            highs = df['high'].astype(float).values
            lows = df['low'].astype(float).values
            volumes = df['volume'].astype(float).values

            ma_params = self.params.get("ma_params", [5, 10, 20, 60])

            # 均线分析
            tech["均线"] = self._analyze_ma(closes, ma_params)

            # MACD分析
            tech["MACD"] = self._analyze_macd(closes)

            # BOLL分析
            tech["BOLL"] = self._analyze_boll(closes)

            # KDJ分析
            tech["KDJ"] = self._analyze_kdj(highs, lows, closes)

            # RSI分析
            tech["RSI"] = self._analyze_rsi(closes)

            # 支撑压力位
            tech["支撑压力"] = self._calc_support_resistance(closes, highs, lows)

            # 量价分析
            tech["量价"] = self._analyze_volume_price(df)

        except Exception as e:
            logger.error(f"技术面分析失败: {e}")
            tech["error"] = str(e)

        return tech

    def _analyze_ma(self, closes: np.ndarray, params: List[int]) -> Dict[str, Any]:
        """均线分析"""
        ma_values = {}
        for period in params:
            if len(closes) >= period:
                ma_values[f"MA{period}"] = round(float(np.mean(closes[-period:])), 2)

        # 多头排列判断
        ma_keys = sorted(ma_values.keys(), key=lambda x: int(x[2:]))
        if len(ma_keys) >= 3:
            ma_vals = [ma_values[k] for k in ma_keys]
            多头排列 = all(ma_vals[i] < ma_vals[i+1] for i in range(len(ma_vals)-1))
        else:
            多头排列 = False

        # 当前价格与均线关系
        current_price = closes[-1]
        above_ma = {k: current_price > v for k, v in ma_values.items()}

        return {
            "数值": ma_values,
            "多头排列": 多头排列,
            "价格位置": {k: round((current_price - v) / v * 100, 2) for k, v in ma_values.items()},
        }

    def _analyze_macd(self, closes: np.ndarray) -> Dict[str, Any]:
        """MACD分析"""
        p = self.params
        fast, slow, signal = p.get("macd_fast", 12), p.get("macd_slow", 26), p.get("macd_signal", 9)

        macd, signal_line, hist = self._calc_macd(closes, fast, slow, signal)

        macd_val = float(macd[-1])
        signal_val = float(signal_line[-1])
        hist_val = float(hist[-1])

        # 金叉死叉判断
        if len(macd) >= 2:
            prev_macd, prev_signal = float(macd[-2]), float(signal_line[-2])
            if macd_val > signal_val and prev_macd <= prev_signal:
               交叉信号 = "金叉"
            elif macd_val < signal_val and prev_macd >= prev_signal:
                交叉信号 = "死叉"
            else:
                交叉信号 = "无交叉"
        else:
            交叉信号 = "数据不足"

        return {
            "DIF": round(macd_val, 3),
            "DEA": round(signal_val, 3),
            "MACD柱": round(hist_val, 3),
            "位置": "0轴上方" if macd_val > 0 else "0轴下方",
            "红柱/绿柱": "红柱" if hist_val > 0 else "绿柱",
            "交叉信号": 交叉信号,
        }

    def _analyze_boll(self, closes: np.ndarray) -> Dict[str, Any]:
        """BOLL分析"""
        period = self.params.get("boll_period", 20)
        std_dev = self.params.get("boll_std", 2)

        if len(closes) < period:
            return {"error": "数据不足"}

        recent = closes[-period:]
        mid = np.mean(recent)
        std = np.std(recent)
        upper = mid + std_dev * std
        lower = mid - std_dev * std

        current = closes[-1]
        position = (current - lower) / (upper - lower) * 100 if upper > lower else 50

        return {
            "上轨": round(upper, 2),
            "中轨": round(mid, 2),
            "下轨": round(lower, 2),
            "当前位置": f"{position:.1f}%",
            "信号": "突破上轨" if current > upper else "突破下轨" if current < lower else "中轨附近",
        }

    def _analyze_kdj(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> Dict[str, Any]:
        """KDJ分析"""
        n = self.params.get("kdj_n", 9)
        m1 = self.params.get("kdj_m1", 3)
        m2 = self.params.get("kdj_m2", 3)

        if len(closes) < n:
            return {"error": "数据不足"}

        kdj_k, kdj_d, kdj_j = self._calc_kdj(highs, lows, closes, n, m1, m2)

        k_val = float(kdj_k[-1])
        d_val = float(kdj_d[-1])
        j_val = float(kdj_j[-1])

        # 超买超卖
        if k_val > 80:
            信号 = "超买"
        elif k_val < 20:
            信号 = "超卖"
        else:
            信号 = "正常"

        # 金叉死叉
        if len(kdj_k) >= 2:
            if k_val > d_val and kdj_k[-2] <= kdj_d[-2]:
                交叉 = "金叉"
            elif k_val < d_val and kdj_k[-2] >= kdj_d[-2]:
                交叉 = "死叉"
            else:
                交叉 = "无"
        else:
            交叉 = "数据不足"

        return {
            "K": round(k_val, 2),
            "D": round(d_val, 2),
            "J": round(j_val, 2),
            "信号": 信号,
            "交叉": 交叉,
        }

    def _analyze_rsi(self, closes: np.ndarray, periods: List[int] = None) -> Dict[str, Any]:
        """RSI分析"""
        if periods is None:
            periods = [6, 12, 24]

        rsi_values = {}
        for period in periods:
            if len(closes) > period:
                rsi = self._calc_rsi(closes, period)
                rsi_values[f"RSI{period}"] = round(float(rsi[-1]), 2)

        # 综合判断
        if rsi_values:
            avg_rsi = sum(rsi_values.values()) / len(rsi_values)
            if avg_rsi > 70:
                整体信号 = "超买"
            elif avg_rsi < 30:
                整体信号 = "超卖"
            else:
                整体信号 = "正常"
        else:
            整体信号 = "数据不足"

        return {
            "数值": rsi_values,
            "整体信号": 整体信号,
        }

    def _calc_support_resistance(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> Dict[str, Any]:
        """计算支撑位和压力位"""
        # 取近60日数据
        lookback = min(60, len(closes))
        recent_closes = closes[-lookback:]
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]

        # 压力位：前期高点
        # 支撑位：前期低点

        # 找到显著的高点和低点
        high_peaks = []
        low_valleys = []

        for i in range(2, lookback - 2):
            if recent_highs[i] > recent_highs[i-1] and recent_highs[i] > recent_highs[i+1]:
                high_peaks.append(recent_highs[i])
            if recent_lows[i] < recent_lows[i-1] and recent_lows[i] < recent_lows[i+1]:
                low_valleys.append(recent_lows[i])

        # 取最近的几 个重要价位
        current = closes[-1]

        压力1 = min(high_peaks[-3:]) if len(high_peaks) >= 3 else recent_highs.max()
        压力2 = max(high_peaks[-3:]) if len(high_peaks) >= 3 else recent_highs.max()
        支撑1 = max(low_valleys[-3:]) if len(low_valleys) >= 3 else recent_lows.min()
        支撑2 = min(low_valleys[-3:]) if len(low_valleys) >= 3 else recent_lows.min()

        return {
            "压力1": round(float(压力1), 2),
            "压力2": round(float(压力2), 2),
            "支撑1": round(float(支撑1), 2),
            "支撑2": round(float(支撑2), 2),
            "当前价": round(float(current), 2),
        }

    def _analyze_volume_price(self, df: pd.DataFrame) -> Dict[str, Any]:
        """量价分析"""
        try:
            volumes = df['volume'].astype(float).values
            closes = df['close'].astype(float).values

            # 放量上涨/缩量上涨
            vol_5avg = np.mean(volumes[-6:-1])
            vol_today = volumes[-1]
            price_change = (closes[-1] / closes[-2] - 1) * 100 if len(closes) > 1 else 0

            if vol_today > vol_5avg * 1.5 and price_change > 0:
                信号 = "放量上涨"
            elif vol_today > vol_5avg * 1.5 and price_change < 0:
                信号 = "放量下跌"
            elif vol_today < vol_5avg * 0.7 and price_change > 0:
                信号 = "缩量上涨"
            elif vol_today < vol_5avg * 0.7 and price_change < 0:
                信号 = "缩量下跌"
            else:
                信号 = "正常量价配合"

            return {
                "信号": 信号,
                "量比": round(vol_today / vol_5avg, 2) if vol_5avg > 0 else 1.0,
            }
        except Exception as e:
            return {"信号": "分析失败", "error": str(e)}

    def _identify_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """识别K线形态"""
        patterns_found = []
        signals = []

        try:
            closes = df['close'].astype(float).values
            opens = df['open'].astype(float).values
            highs = df['high'].astype(float).values
            lows = df['low'].astype(float).values

            # 检查最近5根K线
            for i in range(-5, 0):
                if abs(i) > len(closes):
                    break

                o, c, h, l = opens[i], closes[i], highs[i], lows[i]
                body = abs(c - o)
                upper_shadow = h - max(o, c)
                lower_shadow = min(o, c) - l

                # 锤子线（探底回升）
                if lower_shadow > body * 2 and upper_shadow < body * 0.5:
                    patterns_found.append("锤子线")
                    if i == -1:  # 今日
                        signals.append(("看多", "锤子线 - 探底回升信号"))

                # 射击之星（冲高回落）
                if upper_shadow > body * 2 and lower_shadow < body * 0.5:
                    patterns_found.append("射击之星")
                    if i == -1:
                        signals.append(("看空", "射击之星 - 警惕回落"))

                # 十字星
                if body < (h - l) * 0.1:
                    patterns_found.append("十字星")
                    if i == -1:
                        signals.append(("中性", "十字星 - 多空平衡"))

                # 大阳线
                if c > o and body / o > 0.05:
                    if i == -1:
                        signals.append(("看多", "大阳线 - 强势"))

                # 大阴线
                if c < o and body / o > 0.05:
                    if i == -1:
                        signals.append(("看空", "大阴线 - 弱势"))

            # 去重
            patterns_found = list(set(patterns_found))

            # 今日信号优先
            today_signals = [s for s in signals if "今日" in str(s) or s[0] in ["看多", "看空"]]
            if not today_signals:
                today_signals = signals

        except Exception as e:
            logger.debug(f"K线形态识别失败: {e}")
            patterns_found = []
            today_signals = []

        return {
            "识别到的形态": patterns_found,
            "信号": today_signals,
        }

    def _analyze_fundamental(self, symbol: str) -> Dict[str, Any]:
        """基本面分析（简化版）"""
        try:
            info = self.fetcher.get_stock_info(symbol)
            if not info:
                return {"状态": "数据获取失败"}

            # 提取可用信息
            fund = {
                "状态": "数据有限",
                "获取到的信息": {}
            }

            # 过滤有用字段
            useful_keys = ["行业", "总市值", "流通市值", "市盈率", "市净率", "毛利率", "净利润"]
            for key in useful_keys:
                if key in info:
                    fund["获取到的信息"][key] = info[key]

            return fund

        except Exception as e:
            logger.debug(f"基本面分析失败: {e}")
            return {"状态": "分析异常"}

    def _generate_signal_from_warfare(self, warfare_result: Dict[str, Any]) -> Dict[str, Any]:
        """从战法评估结果生成交易信号"""
        signal = warfare_result.get("信号", {})
        composite = warfare_result.get("综合", {})

        return {
            "信号": signal.get("操作", "持有"),
            "强度": signal.get("强度", ""),
            "评分": composite.get("评分", 50),
            "评级": composite.get("评级", "B"),
            "理由": signal.get("理由", []),
            "建议": f"建议{signal.get('操作', '持有')}",
            "止损位": signal.get("止损", "5%"),
            "止盈位": signal.get("止盈", "15%"),
        }

    def _generate_signal(
        self,
        tech: Dict[str, Any],
        patterns: Dict[str, Any],
        fund: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成综合交易信号"""
        score = 50  # 基础分
        reasons = []
        signal_level = "持有"

        try:
            # 技术面打分
            if tech.get("均线", {}).get("多头排列"):
                score += 15
                reasons.append("均线多头排列")

            macd = tech.get("MACD", {})
            if macd.get("位置") == "0轴上方":
                score += 10
                reasons.append("MACD在0轴上方")
            if macd.get("交叉信号") == "金叉":
                score += 15
                reasons.append("MACD金叉")

            bollinger = tech.get("BOLL", {})
            if "突破" in bollinger.get("信号", ""):
                if "上轨" in bollinger.get("信号", ""):
                    score += 5
                else:
                    score -= 5

            kdj = tech.get("KDJ", {})
            if kdj.get("信号") == "超卖":
                score += 10
                reasons.append("KDJ超卖")
            elif kdj.get("信号") == "超买":
                score -= 10
                reasons.append("KDJ超买")
            if kdj.get("交叉") == "金叉":
                score += 10

            # K线形态
            pattern_signals = patterns.get("信号", [])
            for p_signal in pattern_signals:
                if p_signal[0] == "看多":
                    score += 10
                    reasons.append(p_signal[1])
                elif p_signal[0] == "看空":
                    score -= 10
                    reasons.append(p_signal[1])

            # 最终信号
            if score >= 70:
                signal_level = "买入"
            elif score >= 55:
                signal_level = "加仓"
            elif score >= 45:
                signal_level = "持有"
            elif score >= 30:
                signal_level = "减仓"
            else:
                signal_level = "卖出"

        except Exception as e:
            logger.debug(f"信号生成失败: {e}")

        # 止损止盈
        止损 = self.params.get("止损比例", 0.05)
        止盈 = self.params.get("止盈比例", 0.15)

        return {
            "信号": signal_level,
            "评分": round(score, 1),
            "理由": reasons,
            "建议": f"建议{signal_level}",
            "止损位": f"{止损*100:.0f}%",
            "止盈位": f"{止盈*100:.0f}%",
        }

    # ==================== 技术指标计算工具 ====================

    def _calc_macd(self, prices: np.ndarray, fast: int, slow: int, signal: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
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

    def _calc_kdj(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                  n: int, m1: int, m2: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算KDJ"""
        kdj_k = np.zeros(len(closes))
        kdj_d = np.zeros(len(closes))
        kdj_j = np.zeros(len(closes))

        for i in range(n - 1, len(closes)):
            recent_high = max(highs[i - n + 1:i + 1])
            recent_low = min(lows[i - n + 1:i + 1])

            if recent_high > recent_low:
                rsv = (closes[i] - recent_low) / (recent_high - recent_low) * 100
            else:
                rsv = 50

            if i == n - 1:
                kdj_k[i] = rsv
            else:
                kdj_k[i] = (m1 - 1) / m1 * kdj_k[i - 1] + rsv / m1

            kdj_d[i] = (m1 - 1) / m1 * kdj_d[i - 1] + kdj_k[i] / m1
            kdj_j[i] = m2 * kdj_k[i] - (m2 - 1) * kdj_d[i]

        return kdj_k, kdj_d, kdj_j

    def _calc_rsi(self, prices: np.ndarray, period: int) -> np.ndarray:
        """计算RSI"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return np.array([100.0])

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return np.array([rsi])


# 单例
_analyzer_instance = None

def get_analyzer(params: Dict[str, Any] = None) -> StockAnalyzer:
    """获取分析器单例"""
    global _analyzer_instance
    if _analyzer_instance is None or params:
        _analyzer_instance = StockAnalyzer(params)
    return _analyzer_instance
