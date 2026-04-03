"""
综合战法系统 - 整合9本实战书籍的核心经验
基于《短线操盘》《交易真相》《股市扫地僧》《量学》《一买即涨》《股道人生》等

战法核心思想：
1. 只做强势股（主力资金运作）
2. 趋势为王，顺势而为
3. 截断亏损，让利润奔跑
4. 仓位管理是生命线
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class ComprehensiveWarfare:
    """
    综合战法 - 多维度股票评估系统

    评估维度：
    1. 趋势维度 - 均线系统、趋势线
    2. 动量维度 - MACD、KDJ、RSI
    3. 量价维度 - 成交量、量比、换手率
    4. 形态维度 - K线形态、突破形态
    5. 位置维度 - BOLL、相对位置
    6. 情绪维度 - 涨停基因、板块联动
    7. 基本面维度 - 市值、行业、财务指标
    """

    def __init__(self):
        pass

    def evaluate(self, df: pd.DataFrame, info: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        综合评估股票

        Returns:
            包含各维度评分和综合信号的字典
        """
        if df is None or len(df) < 20:
            return {"error": "数据不足"}

        result = {}
        result["_df"] = df  # 保存原始数据用于止盈止损计算

        # 1. 趋势评估
        result["趋势"] = self._evaluate_trend(df)

        # 2. 动量评估
        result["动量"] = self._evaluate_momentum(df)

        # 3. 量价评估
        result["量价"] = self._evaluate_volume_price(df)

        # 4. 形态评估
        result["形态"] = self._evaluate_patterns(df)

        # 5. 位置评估
        result["位置"] = self._evaluate_position(df)

        # 6. 情绪评估
        result["情绪"] = self._evaluate_sentiment(df)

        # 7. 综合评分
        result["综合"] = self._calculate_composite_score(result)

        # 8. 生成交易信号
        result["信号"] = self._generate_trade_signal(result)

        return result

    def _evaluate_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """趋势维度评估"""
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values

        # 计算均线
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else ma20

        details["MA5"] = round(ma5, 2)
        details["MA10"] = round(ma10, 2)
        details["MA20"] = round(ma20, 2)
        details["MA60"] = round(ma60, 2)

        # 均线多头排列（来自《短线操盘》《股道人生》）
        if ma5 > ma10 > ma20:
            score += 20
            details["多头排列"] = "强多头"
        elif ma5 > ma10:
            score += 10
            details["多头排列"] = "弱多头"
        elif ma5 < ma10 < ma20:
            score -= 15
            details["多头排列"] = "空头"
        else:
            details["多头排列"] = "震荡"

        # 价格与均线关系
        current_price = closes[-1]
        if current_price > ma5:
            score += 5
        if current_price > ma20:
            score += 5
        if current_price > ma60:
            score += 5

        # 上升趋势（来自《交易真相》- 阶梯理论）
        # 定义：价格在各均线上方，未形成连续下降阶梯
        if current_price > ma5 > ma10 > ma20:
            score += 10
            details["趋势判断"] = "上升趋势"
        elif current_price < ma5 < ma10 < ma20:
            score -= 10
            details["趋势判断"] = "下降趋势"
        else:
            details["趋势判断"] = "震荡整理"

        # 限制分数范围
        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    def _evaluate_momentum(self, df: pd.DataFrame) -> Dict[str, Any]:
        """动量维度评估"""
        score = 50
        details = {}

        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values

        # MACD评估（来自《都市》《一买即涨》《量学》）
        macd, signal, hist = self._calc_macd(closes)
        macd_val = float(macd[-1]) if len(macd) > 0 else 0
        signal_val = float(signal[-1]) if len(signal) > 0 else 0
        hist_val = float(hist[-1]) if len(hist) > 0 else 0

        details["DIF"] = round(macd_val, 3)
        details["DEA"] = round(signal_val, 3)
        details["MACD柱"] = round(hist_val, 3)

        # MACD在0轴上方（《都市》经验）
        if macd_val > 0:
            score += 15
            details["MACD位置"] = "0轴上方"
        else:
            details["MACD位置"] = "0轴下方"

        # MACD红柱（动量向上）
        if hist_val > 0:
            score += 5
            details["MACD动量"] = "红柱"
        else:
            details["MACD动量"] = "绿柱"

        # MACD金叉/死叉
        if len(macd) >= 2:
            if macd_val > signal_val and macd[-2] <= signal[-2]:
                score += 15
                details["MACD交叉"] = "金叉"
            elif macd_val < signal_val and macd[-2] >= signal[-2]:
                score -= 10
                details["MACD交叉"] = "死叉"
            else:
                details["MACD交叉"] = "无交叉"
        else:
            details["MACD交叉"] = "数据不足"

        # KDJ评估（来自《一买即涨》）
        k, d, j = self._calc_kdj(highs, lows, closes)
        k_val = float(k[-1]) if len(k) > 0 else 50
        d_val = float(d[-1]) if len(d) > 0 else 50
        j_val = float(j[-1]) if len(j) > 0 else 50

        details["K"] = round(k_val, 2)
        details["D"] = round(d_val, 2)
        details["J"] = round(j_val, 2)

        # KDJ超卖反弹（《一买即涨》- BIAS超卖反弹的变体）
        if k_val < 20:
            score += 10
            details["KDJ信号"] = "超卖反弹"
        elif k_val > 80:
            score -= 5
            details["KDJ信号"] = "超买"
        else:
            details["KDJ信号"] = "正常"

        # KDJ金叉
        if len(k) >= 2:
            if k_val > d_val and k[-2] <= d[-2]:
                score += 10
                details["KDJ交叉"] = "金叉"
            elif k_val < d_val and k[-2] >= d[-2]:
                score -= 5
                details["KDJ交叉"] = "死叉"
            else:
                details["KDJ交叉"] = "无"
        else:
            details["KDJ交叉"] = "数据不足"

        # RSI评估
        rsi = self._calc_rsi(closes)
        rsi_val = float(rsi[-1]) if len(rsi) > 0 else 50
        details["RSI"] = round(rsi_val, 2)

        if rsi_val > 70:
            score -= 5
            details["RSI信号"] = "超买"
        elif rsi_val < 30:
            score += 5
            details["RSI信号"] = "超卖"
        else:
            details["RSI信号"] = "正常"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    def _evaluate_volume_price(self, df: pd.DataFrame) -> Dict[str, Any]:
        """量价维度评估（来自《量学》核心思想）"""
        score = 50
        details = {}

        try:
            volumes = df['volume'].astype(float).values
            closes = df['close'].astype(float).values
            pct_changes = df['pct_change'].astype(float).values if 'pct_change' in df.columns else df['close'].pct_change().values * 100

            # 量比计算
            vol_5avg = np.mean(volumes[-6:-1]) if len(volumes) > 5 else volumes[-1]
            vol_today = volumes[-1]
            vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1

            details["量比"] = round(vol_ratio, 2)

            # 放量上涨（《量学》核心：量为价先）
            price_change = pct_changes[-1] if len(pct_changes) > 0 else 0

            if vol_ratio > 1.5 and price_change > 0:
                score += 15
                details["量价信号"] = "放量上涨"
            elif vol_ratio > 1.5 and price_change < 0:
                score -= 10
                details["量价信号"] = "放量下跌"
            elif vol_ratio < 0.7 and price_change > 0:
                score += 5
                details["量价信号"] = "缩量上涨"
            elif vol_ratio < 0.7 and price_change < 0:
                score += 5
                details["量价信号"] = "缩量下跌（可能见底）"
            else:
                details["量价信号"] = "正常量价"

            # 持续放量判断（《量学》- 高量柱代表主力实力）
            recent_vol = volumes[-5:]
            if all(vol > np.mean(volumes[-20:-5]) for vol in recent_vol):
                score += 10
                details["持续放量"] = "是"
            else:
                details["持续放量"] = "否"

            # 换手率（来自《短线操盘》《股道人生》）
            # 换手率 > 3% 表示活跃
            # 注意：Tushare的pct_change是涨跌幅，需要用成交量估算
            avg_vol = np.mean(volumes[-5:])
            if avg_vol > 500000:  # 成交量较大的股票
                score += 5
                details["活跃度"] = "活跃"
            elif avg_vol < 100000:
                score -= 5
                details["活跃度"] = "低迷"

        except Exception as e:
            logger.debug(f"量价评估异常: {e}")
            details["量价信号"] = "评估异常"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    def _evaluate_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """形态维度评估"""
        score = 50
        details = {"形态": []}

        try:
            closes = df['close'].astype(float).values
            opens = df['open'].astype(float).values
            highs = df['high'].astype(float).values
            lows = df['low'].astype(float).values

            # 检查最近5根K线
            for i in range(-5, 0):
                if abs(i) > len(closes):
                    break

                o, c, h, l = float(opens[i]), float(closes[i]), float(highs[i]), float(lows[i])
                body = abs(c - o)
                upper_shadow = h - max(o, c)
                lower_shadow = min(o, c) - l
                full_range = h - l

                if full_range == 0:
                    continue

                # 锤子线（《一买即涨》- 双针探底变体）
                # 特征：下影线是实体的2倍以上，上影线很短
                if lower_shadow > body * 2 and upper_shadow < body * 0.5:
                    details["形态"].append("锤子线")
                    if i == -1:
                        score += 15
                        details["今日形态"] = "锤子线（探底回升）"

                # 早晨之星（《短线操盘》- 经典反转形态）
                if i == -3:  # 检查连续3根K线
                    pass  # 简化判断

                # 突破前期高点（《短线操盘》《一买即涨》- 横盘突破）
                if i == -1:
                    recent_high = max(highs[-20:-1])
                    if h > recent_high:
                        score += 15
                        details["形态"].append("突破前期高点")
                        details["今日形态"] = "突破新高"

                # 大阳线（强势信号）
                if c > o and body / o > 0.05:
                    if i == -1:
                        score += 10
                        details["今日形态"] = "大阳线"

                # 大阴线（弱势信号）
                if c < o and body / o > 0.05:
                    if i == -1:
                        score -= 10
                        details["今日形态"] = "大阴线"

            # 缺口评估（来自《短线操盘》- 缺口理论）
            if len(closes) >= 2:
                gap = closes[-2] - lows[-1] if closes[-2] > highs[-1] else 0
                if gap > 0:
                    score += 10
                    details["形态"].append("向上跳空缺口")

        except Exception as e:
            logger.debug(f"形态评估异常: {e}")

        if not details["形态"]:
            details["形态"].append("无明显形态")

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    def _evaluate_position(self, df: pd.DataFrame) -> Dict[str, Any]:
        """位置维度评估"""
        score = 50
        details = {}

        try:
            closes = df['close'].astype(float).values
            highs = df['high'].astype(float).values
            lows = df['low'].astype(float).values

            # BOLL评估（来自《一买即涨》《短线操盘》）
            boll_period = 20
            if len(closes) >= boll_period:
                recent = closes[-boll_period:]
                mid = np.mean(recent)
                std = np.std(recent)
                upper = mid + 2 * std
                lower = mid - 2 * std

                current = closes[-1]
                position = (current - lower) / (upper - lower) * 100 if upper > lower else 50

                details["上轨"] = round(upper, 2)
                details["中轨"] = round(mid, 2)
                details["下轨"] = round(lower, 2)
                details["BOLL位置"] = f"{position:.1f}%"

                # BOLL开口判断
                if position > 80:
                    score -= 5
                    details["BOLL信号"] = "上轨附近，注意回调"
                elif position < 20:
                    score += 10
                    details["BOLL信号"] = "下轨附近，可能反弹"
                else:
                    score += 5
                    details["BOLL信号"] = "中轨附近"

            # 相对位置评估（创多少日新高/新低）
            high_20 = max(highs[-20:])
            low_20 = min(lows[-20:])
            current_price = closes[-1]

            if high_20 > 0:
                high_position = (current_price - low_20) / (high_20 - low_20) * 100
                details["20日高位占比"] = f"{high_position:.1f}%"

                if high_position > 90:
                    score -= 5  # 接近20日新高，可能有压力
                elif high_position < 20:
                    score -= 5  # 接近20日新低，可能继续下跌

        except Exception as e:
            logger.debug(f"位置评估异常: {e}")

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    def _evaluate_sentiment(self, df: pd.DataFrame) -> Dict[str, Any]:
        """情绪维度评估"""
        score = 50
        details = {}

        try:
            closes = df['close'].astype(float).values
            pct_changes = df['pct_change'].astype(float).values if 'pct_change' in df.columns else df['close'].pct_change().values * 100

            # 涨停基因（来自《股道人生》《短线操盘》）
            # 10日内有涨停 = 强势股
            limit_up_count = 0
            for pct in pct_changes[-10:]:
                if pct >= 9.5:
                    limit_up_count += 1

            details["10日涨停次数"] = limit_up_count

            if limit_up_count >= 2:
                score += 25
                details["涨停基因"] = "强"
            elif limit_up_count == 1:
                score += 15
                details["涨停基因"] = "有"
            else:
                # 检查接近涨停
                near_limit = sum(1 for pct in pct_changes[-10:] if pct >= 7)
                if near_limit >= 2:
                    score += 10
                    details["涨停基因"] = "接近"
                else:
                    details["涨停基因"] = "无"

            # 近期涨幅（来自《交易真相》- 趋势加速）
            pct_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) > 5 else 0
            details["5日涨幅"] = f"{pct_5d:.2f}%"

            if 3 < pct_5d < 15:
                score += 10
                details["短期强度"] = "健康上涨"
            elif pct_5d >= 15:
                score += 5
                details["短期强度"] = "强势但注意回调"
            elif pct_5d < -10:
                score -= 10
                details["短期强度"] = "弱势"

            # 连续上涨/下跌
            up_days = 0
            down_days = 0
            for pct in pct_changes[-5:]:
                if pct > 0:
                    up_days += 1
                elif pct < 0:
                    down_days += 1

            if up_days >= 4:
                score += 5
                details["连涨"] = f"{up_days}连涨"
            elif down_days >= 4:
                score -= 5
                details["连跌"] = f"{down_days}连跌"

        except Exception as e:
            logger.debug(f"情绪评估异常: {e}")

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    def _calculate_composite_score(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """计算综合评分"""
        # 权重配置（可调整）
        weights = self._load_weights()

        total_score = 0
        for dim, weight in weights.items():
            if dim in result:
                dim_score = result[dim].get("评分", 50)
                total_score += dim_score * weight

        # 综合评分
        composite = round(total_score, 1)

        # 评级
        if composite >= 80:
            rating = "A"
            rating_desc = "强势"
        elif composite >= 65:
            rating = "B+"
            rating_desc = "较好"
        elif composite >= 50:
            rating = "B"
            rating_desc = "一般"
        elif composite >= 35:
            rating = "C"
            rating_desc = "较弱"
        else:
            rating = "D"
            rating_desc = "弱势"

        return {
            "评分": composite,
            "评级": rating,
            "描述": rating_desc,
            "权重": weights
        }

    def _generate_trade_signal(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成交易信号

        基于综合评分和各维度评分，生成操作建议
        """
        composite = result.get("综合", {}).get("评分", 50)
        trend_score = result.get("趋势", {}).get("评分", 50)
        momentum_score = result.get("动量", {}).get("评分", 50)
        vol_price_score = result.get("量价", {}).get("评分", 50)
        pattern_score = result.get("形态", {}).get("评分", 50)
        position_score = result.get("位置", {}).get("评分", 50)
        sentiment_score = result.get("情绪", {}).get("评分", 50)

        # 操作信号判断
        if composite >= 75:
            operation = "买入"
        elif composite >= 65:
            if momentum_score >= 60:
                operation = "加仓"
            else:
                operation = "买入"
        elif composite >= 55:
            if trend_score >= 60:
                operation = "持有/加仓"
            else:
                operation = "持有"
        elif composite >= 40:
            operation = "持有"
        else:
            operation = "减仓"

        # 买入理由
        reasons = []
        if trend_score >= 65:
            reasons.append("均线多头排列")
        if momentum_score >= 65:
            reasons.append("动量强势")
        if vol_price_score >= 65:
            reasons.append("量价配合良好")
        if pattern_score >= 65:
            reasons.append("形态良好")
        if position_score >= 65:
            reasons.append("价格位置有利")
        if sentiment_score >= 65:
            reasons.append("市场情绪积极")

        if not reasons:
            reasons.append(f"综合评分{int(composite)}分")

        # 动态止盈止损
        stop_loss, take_profit, sl_tp_reason = self._calculate_dynamic_stops(result)

        return {
            "操作": operation,
            "理由": reasons,
            "止损": stop_loss,
            "止盈": take_profit,
            "止盈止损依据": sl_tp_reason
        }

    def _load_weights(self) -> Dict[str, float]:
        """从配置文件加载权重，支持自动调整"""
        import json
        from pathlib import Path

        config_path = Path(__file__).parent.parent / "Stock Verification" / "warfare_config.json"
        default_weights = {
            "趋势": 0.25,
            "动量": 0.20,
            "量价": 0.20,
            "形态": 0.15,
            "位置": 0.10,
            "情绪": 0.10,
        }

        if not config_path.exists():
            return default_weights

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get("weights", default_weights)
        except Exception:
            return default_weights

    def _calculate_dynamic_stops(self, result: Dict[str, Any]) -> Tuple[str, str, str]:
        """
        动态计算止损止盈位

        基于九本书理论，结合多种因素：
        1. 前高位置（《一买即涨》- 接近前高有压力）
        2. BOLL位置（《一买即涨》- BOLL上下轨参考）
        3. 历史波动率（《交易真相》- 截断亏损）
        4. 均线支撑（《短线操盘》- 均线系统）

        Returns:
            (止损字符串, 止盈字符串, 计算依据)
        """
        df = result.get("_df")
        if df is None or len(df) < 20:
            return "5%", "15%", "数据不足，使用默认"

        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values
        current_price = closes[-1]

        # ============ 止盈位计算 ============
        # 因素1：前高位置（目标位）
        high_20 = max(highs[-20:])
        high_50 = max(highs[-50:]) if len(highs) >= 50 else high_20
        recent_high = max(highs[-10:])

        # 因素2：BOLL上轨
        boll_period = 20
        if len(closes) >= boll_period:
            recent = closes[-boll_period:]
            mid = np.mean(recent)
            std = np.std(recent)
            boll_upper = mid + 2 * std
            boll_lower = mid - 2 * std
        else:
            boll_upper = high_20
            boll_lower = lows[-20:].min() if len(lows) >= 20 else current_price * 0.95

        # 因素3：历史波动率（ATR简化版）
        true_ranges = []
        for i in range(-20, 0):
            if i + 1 >= -len(lows):
                tr = max(highs[i] - lows[i],
                        abs(highs[i] - closes[i-1]),
                        abs(lows[i] - closes[i-1]))
                true_ranges.append(tr)
        atr = np.mean(true_ranges) if true_ranges else current_price * 0.02
        atr_pct = atr / current_price * 100

        # 因素4：均线阻力（MA20）
        ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else current_price
        ma10 = np.mean(closes[-10:]) if len(closes) >= 10 else current_price

        # ============ 计算止盈位 ============
        # 综合目标位：取前高和BOLL上轨的较小值（保守估计）
        # 如果已经突破20日新高，止盈目标设为50日新高
        distance_from_20high = (high_20 - current_price) / current_price * 100

        if distance_from_20high < 3:
            # 已经接近20日新高，止盈目标看50日新高
            target_high = high_50
            target_name = "50日新高"
        else:
            # 距离20日新高还有空间
            target_high = high_20
            target_name = "20日新高"

        # BOLL上轨目标
        boll_target = boll_upper

        # 取较小的作为第一止盈目标（保守）
        primary_take_profit = min(target_high, boll_target)
        primary_tp_pct = (primary_take_profit - current_price) / current_price * 100

        # 如果距离目标太近（<5%），扩展到均线系统的上方空间
        if primary_tp_pct < 5:
            # 扩大止盈目标到：当前位置 + 1.5倍ATR
            extended_target = current_price + atr * 1.5
            primary_take_profit = extended_target
            primary_tp_pct = (extended_target - current_price) / current_price * 100
            target_name = f"{target_name}+1.5ATR"

        # ============ 计算止损位 ============
        # 止损位取：均线支撑和BOLL下轨的较弱者（严格执行）
        ma10_dist = (current_price - ma10) / current_price * 100
        ma20_dist = (current_price - ma20) / current_price * 100

        # BOLL下轨止损
        boll_stop_pct = (current_price - boll_lower) / current_price * 100

        # 前低止损（10日最低）
        low_10 = min(lows[-10:]) if len(lows) >= 10 else lows[-1]
        recent_low_stop_pct = (current_price - low_10) / current_price * 100

        # 综合止损：《交易真相》截断亏损原则，取最保守的止损位
        # 正常止损：不超过2倍ATR
        max_stop = current_price - atr * 2

        # 取以下几个中的最小值（最严格）：
        # 1. BOLL下轨
        # 2. 10日最低点
        # 3. MA10支撑（如果跌破MA10）
        candidates = [
            (boll_lower, "BOLL下轨"),
            (low_10, "10日最低"),
            (ma10, "MA10支撑"),
        ]

        # 选择最低的作为止损位（最保守）
        best_stop = max(candidates, key=lambda x: x[0])[0]  # 这里选择价格最低的
        # 实际上要选跌破风险最大的，即支撑最弱的
        # 重新选择：哪个支撑位最低（最容易被跌破）
        stop_candidates = [
            (boll_lower, boll_stop_pct, "BOLL下轨"),
            (low_10, recent_low_stop_pct, "10日最低"),
        ]

        # 选择跌破概率最大、跌幅最大的那个
        best_stop_price = min([c[0] for c in stop_candidates])
        best_stop_name = [c[2] for c in stop_candidates if c[0] == best_stop_price][0]
        best_stop_pct = (current_price - best_stop_price) / current_price * 100

        # 限制止损不超过2倍ATR（如果ATR计算的止损更合理）
        atr_stop_price = current_price - atr * 2
        if atr_stop_price > best_stop_price:
            # ATR止损更合理（更宽松）
            final_stop_price = atr_stop_price
            final_stop_name = "2倍ATR"
            final_stop_pct = 2 * atr_pct
        else:
            final_stop_price = best_stop_price
            final_stop_name = best_stop_name
            final_stop_pct = best_stop_pct

        # 如果止损太大（>8%），强制限制到8%（《股道人生》止损7-8%原则）
        if final_stop_pct > 8:
            final_stop_price = current_price * (1 - 0.08)
            final_stop_name = "8%止损上限"
            final_stop_pct = 8.0

        # 如果止损太小（<3%），放宽到MA20支撑
        if final_stop_pct < 3:
            ma20_stop = current_price - atr * 1.5
            ma20_stop_pct = (current_price - ma20_stop) / current_price * 100
            if ma20_stop_pct <= 8:
                final_stop_price = ma20_stop
                final_stop_name = "MA20/1.5倍ATR"
                final_stop_pct = ma20_stop_pct

        # ============ 生成止盈止损字符串 ============
        take_profit_str = f"{primary_tp_pct:.0f}-{primary_tp_pct*1.5:.0f}%" if primary_tp_pct < 10 else f"{primary_tp_pct:.0f}%"

        stop_loss_str = f"{final_stop_pct:.1f}%"

        reason = (f"止盈依据：{target_name} {primary_tp_pct:.1f}%，"
                 f"止损依据：{final_stop_name} {final_stop_pct:.1f}%，"
                 f"ATR波动 {atr_pct:.1f}%")

        return stop_loss_str, take_profit_str, reason
        composite = result.get("综合", {}).get("评分", 50)

        signal = {}
        reasons = []

        # 买入信号
        if composite >= 70:
            signal["操作"] = "买入"
            signal["强度"] = "强烈推荐"

            if result.get("趋势", {}).get("详情", {}).get("多头排列") == "强多头":
                reasons.append("均线多头排列")
            if result.get("动量", {}).get("详情", {}).get("MACD交叉") == "金叉":
                reasons.append("MACD金叉")
            if result.get("量价", {}).get("详情", {}).get("量价信号") == "放量上涨":
                reasons.append("放量上涨")
            if result.get("形态", {}).get("详情", {}).get("今日形态") == "突破新高":
                reasons.append("突破新高")
            if result.get("情绪", {}).get("详情", {}).get("涨停基因") in ["强", "有"]:
                reasons.append("有涨停基因")

        elif composite >= 55:
            signal["操作"] = "持有/加仓"
            signal["强度"] = "建议关注"

            if result.get("趋势", {}).get("详情", {}).get("多头排列") in ["强多头", "弱多头"]:
                reasons.append("均线多头")
            if result.get("动量", {}).get("详情", {}).get("MACD位置") == "0轴上方":
                reasons.append("MACD强势")
            if result.get("位置", {}).get("详情", {}).get("BOLL信号") == "下轨附近，可能反弹":
                reasons.append("BOLL下轨反弹")
            if result.get("量价", {}).get("详情", {}).get("量价信号") == "放量上涨":
                reasons.append("量价配合好")
            if result.get("情绪", {}).get("详情", {}).get("涨停基因") in ["强", "有"]:
                reasons.append("有涨停基因")

            # 如果仍无理由，添加综合评分说明
            if not reasons:
                reasons.append(f"综合评分{composite}分，趋势待确认")

        elif composite >= 40:
            signal["操作"] = "持有观望"
            signal["强度"] = "谨慎"

            if result.get("趋势", {}).get("详情", {}).get("趋势判断") == "震荡整理":
                reasons.append("震荡整理")

        else:
            signal["操作"] = "减仓/观望"
            signal["强度"] = "建议回避"

            if result.get("趋势", {}).get("详情", {}).get("多头排列") == "空头":
                reasons.append("均线空头排列")
            if result.get("动量", {}).get("详情", {}).get("KDJ信号") == "超买":
                reasons.append("KDJ超买")
            if result.get("情绪", {}).get("详情", {}).get("涨停基因") == "无":
                reasons.append("无涨停基因")

        # 止损止盈建议（动态计算）
        stop_loss, take_profit, sl_tp_reason = self._calculate_dynamic_stops(result)
        signal["止损"] = stop_loss
        signal["止盈"] = take_profit
        signal["止盈止损依据"] = sl_tp_reason

        signal["理由"] = reasons

        return signal

    # ==================== 技术指标计算工具 ====================

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

    def _calc_kdj(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                   n: int = 9, m1: int = 3, m2: int = 3) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
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

    def _calc_rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
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
_warfare_instance = None

def get_warfare() -> ComprehensiveWarfare:
    """获取战法单例"""
    global _warfare_instance
    if _warfare_instance is None:
        _warfare_instance = ComprehensiveWarfare()
    return _warfare_instance
