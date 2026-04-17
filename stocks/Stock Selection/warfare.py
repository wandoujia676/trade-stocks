"""
综合战法系统 - 小金库 5.1 纯左侧战法
核心思想：买在分歧，卖在一致
在股票还没有大幅拉升的阶段提前潜伏，等待反弹或反转

左侧战法核心：
1. 超跌反弹（RSI < 30，BOLL下轨）
2. 均线蓄势（空头排列收敛，即将转多头）
3. 地量见底（卖压枯竭）
4. 底部放量（主力吸筹）
5. MACD即将金叉（动量转多前兆）
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class ComprehensiveWarfare:
    """
    综合战法 - 多维度股票评估系统（纯左侧模式）

    评估维度：
    1. 趋势维度 - 均线蓄势、收敛、即将转多
    2. 动量维度 - MACD绿柱缩短、即将金叉
    3. 左侧维度 - RSI超卖、BOLL下轨、负乖离率
    4. 量价维度 - 地量见底、底部放量
    5. 形态维度 - 锤子线、探底形态
    6. 位置维度 - 低位、接近支撑
    7. 情绪维度 - 涨停基因、主力异动
    """

    def __init__(self):
        pass

    def evaluate(self, df: pd.DataFrame, info: Dict[str, Any] = None, mode: str = "wave") -> Dict[str, Any]:
        """
        综合评估股票

        Args:
            df: 股票日线数据
            info: 附加信息（如实时价格等）
            mode: 战法模式
                - "wave": 波段主升浪（默认，右侧顺势）
                - "left": 纯左侧战法（超跌反弹）

        Returns:
            包含各维度评分和综合信号的字典
        """
        if df is None or len(df) < 20:
            return {"error": "数据不足"}

        result = {}
        result["_df"] = df  # 保存原始数据用于止盈止损计算
        result["战法模式"] = mode

        if mode == "wave":
            # ============ 波段主升浪战法 ============
            # 核心：买在整理后的突破启动点，捕捉主升浪

            # 1. 趋势评估 - 均线从收敛转向发散
            result["趋势"] = self._evaluate_trend_wave(df)

            # 2. 动量评估 - MACD金叉/红柱放大
            result["动量"] = self._evaluate_momentum_wave(df)

            # 3. 量价评估 - 放量突破
            result["量价"] = self._evaluate_volume_price_wave(df)

            # 4. 形态评估 - 整理形态完成/突破
            result["形态"] = self._evaluate_patterns_wave(df)

            # 5. 位置评估 - 相对低位启动（避免追高）
            result["位置"] = self._evaluate_position_wave(df)

            # 6. 情绪评估 - 板块龙头/题材
            result["情绪"] = self._evaluate_sentiment_wave(df)

            # 7. 突破评估 - 突破有效性
            result["突破"] = self._evaluate_breakout_wave(df)

            # 8. 综合评分
            result["综合"] = self._calculate_composite_score_wave(result)

            # 9. 波段启动信号识别
            result["波段信号"] = self._identify_wave_breakout(df)

            # 10. 生成交易信号
            result["信号"] = self._generate_wave_signal(result)

        else:
            # ============ 纯左侧战法（原逻辑）============
            result["战法模式"] = "左侧"

            # 1. 趋势评估 - 均线蓄势/收敛
            result["趋势"] = self._evaluate_trend_left(df)

            # 2. 动量评估 - MACD即将转多
            result["动量"] = self._evaluate_momentum_left(df)

            # 3. 左侧评估（核心！） - 超跌反弹信号
            result["左侧"] = self._evaluate_left_side(df)

            # 4. 量价评估 - 地量见底
            result["量价"] = self._evaluate_volume_price_left(df)

            # 5. 形态评估 - 探底形态
            result["形态"] = self._evaluate_patterns_left(df)

            # 6. 位置评估 - 低位支撑
            result["位置"] = self._evaluate_position_left(df)

            # 7. 情绪评估 - 涨停基因
            result["情绪"] = self._evaluate_sentiment_left(df)

            # 8. 综合评分
            result["综合"] = self._calculate_composite_score_left(result)

            # 9. 左侧启动信号识别
            result["左侧信号"] = self._identify_left_breakout(df)

            # 10. 生成交易信号
            result["信号"] = self._generate_left_signal(result)

        return result

    def evaluate_realtime(self, df: pd.DataFrame, realtime_data: Dict[str, Any], mode: str = "wave") -> Dict[str, Any]:
        """
        实时数据评估（盘中用）

        Args:
            df: 历史日线数据
            realtime_data: 实时行情数据（包含 current, pct_chg, volume 等）
            mode: 战法模式

        Returns:
            评估结果
        """
        if df is None or len(df) < 20:
            return {"error": "数据不足"}

        # 用实时价格替换最后一天的收盘价
        df = df.copy()
        current_price = realtime_data.get('current')
        if current_price:
            df.iloc[-1, df.columns.get_loc('close')] = current_price

        # 重新计算pct_change
        if 'pct_change' in df.columns and len(df) >= 2:
            closes = df['close'].astype(float).values
            df['pct_change'] = pd.Series(closes).pct_change() * 100

        # 调用标准评估
        return self.evaluate(df, info=realtime_data, mode=mode)

    # ==================== 左侧战法：趋势维度 ====================

    def _evaluate_trend_left(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        趋势维度评估 - 左侧战法

        核心：不是看多头排列（那是右侧），而是看均线收敛/蓄势状态
        - 空头排列正在收敛 = 即将转多
        - 均线纠缠 = 蓄势整理
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values

        # 计算均线
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else ma20

        details["MA5"] = round(ma5, 2)
        details["MA10"] = round(ma10, 2)
        details["MA20"] = round(ma20, 2)
        details["MA60"] = round(ma60, 2)

        current_price = closes[-1]

        # ============ 均线蓄势判断（左侧核心！）============

        # 检查均线收敛程度（均线越接近，蓄势越充分）
        ma_spread = abs(ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0
        details["均线收敛度"] = round(ma_spread, 2)

        # 1. 空头排列正在收敛（左侧买入信号！）
        if ma5 < ma10 < ma20:
            # 计算收敛速度
            ma5_before = np.mean(closes[-6:-1]) if len(closes) >= 6 else ma5
            ma10_before = np.mean(closes[-11:-1]) if len(closes) >= 11 else ma10
            ma20_before = np.mean(closes[-21:-1]) if len(closes) >= 21 else ma20

            # 检查是否在收敛
            spread_before = abs(ma5_before - ma10_before) / ma10_before * 100 if ma10_before > 0 else 0

            if ma_spread < spread_before:
                # 正在收敛！
                score += 25
                details["均线状态"] = "空头收敛（蓄势中）"
                details["蓄势信号"] = "即将转多"
            else:
                details["均线状态"] = "空头排列"
                details["蓄势信号"] = "等待收敛"
        # 2. 均线纠缠（蓄势整理）
        elif abs(ma5 - ma10) / ma10 < 3:  # MA5和MA10差距小于3%
            score += 20
            details["均线状态"] = "均线纠缠（蓄势整理）"
            details["蓄势信号"] = "可能突破"
        # 3. 刚刚形成多头排列（已经不是左侧最佳买点）
        elif ma5 > ma10 > ma20:
            score -= 10  # 已经不是最佳左侧买点
            details["均线状态"] = "多头排列（右侧信号）"
            details["蓄势信号"] = "已启动，谨慎追高"
        # 4. 下降趋势中的反弹
        elif current_price < ma20:
            score += 5
            details["均线状态"] = "价格在MA20下方"
            details["蓄势信号"] = "超跌反弹可能"
        else:
            details["均线状态"] = "震荡整理"
            details["蓄势信号"] = "观望"

        # 价格与均线关系
        if current_price < ma5 * 0.95:  # 价格低于MA5 5%以上
            score += 10
            details["价格位置"] = "远离MA5（超跌）"
        elif current_price < ma10:
            score += 5
            details["价格位置"] = "在MA5-MA10之间"
        elif current_price > ma20:
            score -= 5
            details["价格位置"] = "在MA20上方"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 左侧战法：动量维度 ====================

    def _evaluate_momentum_left(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        动量维度评估 - 左侧战法

        核心：不是看已经金叉（右侧），而是看即将金叉/绿柱缩短
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values

        # MACD评估
        macd, signal, hist = self._calc_macd(closes)
        macd_val = float(macd[-1]) if len(macd) > 0 else 0
        signal_val = float(signal[-1]) if len(signal) > 0 else 0
        hist_val = float(hist[-1]) if len(hist) > 0 else 0

        details["DIF"] = round(macd_val, 3)
        details["DEA"] = round(signal_val, 3)
        details["MACD柱"] = round(hist_val, 3)

        # ============ 左侧动量信号============

        # 1. MACD绿柱正在缩短（左侧买入信号！）
        if hist_val < 0:  # 绿柱
            hist_before = float(hist[-2]) if len(hist) >= 2 else 0
            if hist_val > hist_before:  # 绿柱在缩短
                score += 25
                details["MACD状态"] = "绿柱缩短（底部蓄力）"
                details["即将信号"] = "可能形成金叉"
            else:
                score += 10
                details["MACD状态"] = "绿柱（继续等待）"
        # 2. DIF即将上穿DEA（即将金叉！）
        elif len(macd) >= 2:
            macd_before = float(macd[-2])
            signal_before = float(signal[-2])

            if macd_val > signal_val and macd_before <= signal_before:
                # 刚刚金叉
                score += 15
                details["MACD状态"] = "刚刚金叉"
                details["即将信号"] = "金叉确认"
            elif macd_val > signal_val and abs(macd_val - signal_val) < abs(macd_before - signal_before) * 0.5:
                # DIF正在靠近DEA（即将金叉！）
                score += 30
                details["MACD状态"] = "DIF即将上穿DEA"
                details["即将信号"] = "强烈左侧信号"
            elif macd_val > signal_val:
                score += 5
                details["MACD状态"] = "已金叉（右侧）"
            else:
                details["MACD状态"] = "DIF在DEA下方"
        else:
            details["MACD状态"] = "数据不足"

        # 3. DIF在0轴附近但即将突破
        if abs(macd_val) < 0.1 and len(macd) >= 2:
            if macd_val > 0:
                score += 10
                details["0轴信号"] = "DIF在0轴上方（突破在即）"
            else:
                score += 10
                details["0轴信号"] = "DIF在0轴下方（蓄势）"

        # 4. KDJ超卖反弹
        k, d, j = self._calc_kdj(highs, lows, closes)
        k_val = float(k[-1]) if len(k) > 0 else 50

        if k_val < 20:
            score += 20
            details["KDJ信号"] = "深度超卖（强烈反弹信号）"
        elif k_val < 30:
            score += 12
            details["KDJ信号"] = "超卖（可能反弹）"
        elif k_val > 80:
            score -= 10
            details["KDJ信号"] = "超买（注意回调）"

        # 5. RSI超卖
        rsi = self._calc_rsi(closes)
        rsi_val = float(rsi[-1]) if len(rsi) > 0 else 50
        details["RSI"] = round(rsi_val, 2)

        if rsi_val < 25:
            score += 20
            details["RSI信号"] = "深度超卖"
        elif rsi_val < 35:
            score += 10
            details["RSI信号"] = "超卖"
        elif rsi_val > 70:
            score -= 10
            details["RSI信号"] = "超买"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 波段主升浪战法：趋势维度 ====================

    def _evaluate_trend_wave(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        趋势维度评估 - 波段主升浪战法

        核心：均线从收敛/纠缠转向向上发散（多头排列形成中）
        - 不是已经多头排列（那是追高）
        - 而是即将形成多头排列（启动前兆）
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values

        # 计算均线
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else ma20

        details["MA5"] = round(ma5, 2)
        details["MA10"] = round(ma10, 2)
        details["MA20"] = round(ma20, 2)

        current_price = closes[-1]

        # ============ 均线状态判断（波段核心！）============

        # 1. 均线刚刚形成金叉/即将形成多头（最佳启动点！）
        if ma5 > ma10 > ma20:
            # 已经多头排列
            score -= 10
            details["均线状态"] = "多头排列（已启动，谨慎追高）"
            details["蓄势信号"] = "已上涨一段，注意回调"
        elif ma5 > ma10 and ma10 <= ma20:
            # MA5上穿MA10，MA10即将上穿MA20（蓄势突破中！）
            score += 25
            details["均线状态"] = "均线蓄势（MA5上穿MA10）"
            details["蓄势信号"] = "即将形成多头排列"
            # 检查是否在收敛蓄势
            ma5_before = np.mean(closes[-6:-1]) if len(closes) >= 6 else ma5
            ma10_before = np.mean(closes[-11:-1]) if len(closes) >= 11 else ma10
            if ma5 > ma5_before and ma10 > ma10_before:
                score += 10
                details["蓄势信号"] = "均线向上发散，趋势确认"
        elif ma5 < ma10 < ma20:
            # 空头排列，下降趋势
            score -= 15
            details["均线状态"] = "空头排列"
            details["蓄势信号"] = "下降趋势，等待反转"
        else:
            # 均线纠缠（横盘整理）
            ma_spread = abs(ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0
            if ma_spread < 3:
                score += 15
                details["均线状态"] = "均线纠缠（横盘整理）"
                details["蓄势信号"] = "可能选择方向"
            else:
                details["均线状态"] = "震荡整理"
                details["蓄势信号"] = "观望"

        # ============ 价格与均线关系 ============
        if current_price > ma5:
            score += 10
            details["价格位置"] = "在MA5上方（强势）"
        elif current_price > ma20:
            score += 5
            details["价格位置"] = "在MA20上方"
        else:
            details["价格位置"] = "在MA20下方"

        # ============ 均线多头排列强度 ============
        if ma5 > ma10 > ma20:
            # 多头排列强度
            alignment = (ma5 - ma10) / ma10 + (ma10 - ma20) / ma20
            if alignment < 0.02:
                score += 5
                details["多头强度"] = "刚刚形成（启动确认）"
            else:
                details["多头强度"] = "稳定多头"
        else:
            details["多头强度"] = "未形成"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 波段主升浪战法：动量维度 ====================

    def _evaluate_momentum_wave(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        动量维度评估 - 波段主升浪战法

        核心：MACD金叉 + 红柱放大（动能启动）
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values

        # MACD评估
        macd, signal, hist = self._calc_macd(closes)
        macd_val = float(macd[-1]) if len(macd) > 0 else 0
        signal_val = float(signal[-1]) if len(signal) > 0 else 0
        hist_val = float(hist[-1]) if len(hist) > 0 else 0

        details["DIF"] = round(macd_val, 3)
        details["DEA"] = round(signal_val, 3)
        details["MACD柱"] = round(hist_val, 3)

        # ============ MACD金叉/红柱状态============

        # 1. 刚刚金叉（最佳启动点！）
        if len(macd) >= 2:
            macd_before = float(macd[-2])
            signal_before = float(signal[-2])

            if macd_val > signal_val and macd_before <= signal_before:
                # 刚刚金叉
                score += 30
                details["MACD状态"] = "刚刚金叉（启动确认！）"
            elif macd_val > signal_val:
                diff = macd_val - signal_val
                if diff < 0.1:
                    # 靠近0轴的金叉（最强启动）
                    score += 25
                    details["MACD状态"] = "金叉+0轴附近（强势启动）"
                else:
                    # 已金叉一段时间
                    hist_before = float(hist[-2]) if len(hist) >= 2 else 0
                    if hist_val > 0 and hist_val > hist_before:
                        score += 15
                        details["MACD状态"] = "金叉+红柱放大（趋势确认）"
                    else:
                        score += 5
                        details["MACD状态"] = "已金叉"
            elif macd_val < signal_val and macd_before >= signal_before:
                # 刚刚死叉
                score -= 15
                details["MACD状态"] = "刚刚死叉（注意风险）"
            else:
                # DIF在DEA下方
                score -= 5
                details["MACD状态"] = "DIF在DEA下方"
        else:
            details["MACD状态"] = "数据不足"

        # ============ 红柱/绿柱状态 ============
        if hist_val > 0:
            if len(hist) >= 2:
                hist_before = float(hist[-2])
                if hist_val > hist_before:
                    score += 10
                    details["红柱状态"] = "红柱放大（动能增强）"
                else:
                    details["红柱状态"] = "红柱缩短（注意回调）"
            else:
                details["红柱状态"] = "红柱"
        else:
            score -= 10
            details["红柱状态"] = "绿柱（弱势）"

        # ============ DIF与0轴关系 ============
        if macd_val > 0 and macd_val < 0.2:
            score += 10
            details["0轴信号"] = "DIF在0轴上方蓄势"
        elif macd_val > 0.2:
            details["0轴信号"] = "DIF高位（可能调整）"
        else:
            details["0轴信号"] = "DIF在0轴下方"

        # ============ KDJ顺势 ============
        k, d, j = self._calc_kdj(highs, lows, closes)
        k_val = float(k[-1]) if len(k) > 0 else 50

        if 40 < k_val < 70:
            score += 10
            details["KDJ信号"] = "KDJ强势区（顺势）"
        elif k_val >= 70:
            score -= 5
            details["KDJ信号"] = "KDJ超买"
        elif k_val < 30:
            details["KDJ信号"] = "KDJ超卖"

        # ============ RSI顺势 ============
        rsi = self._calc_rsi(closes)
        rsi_val = float(rsi[-1]) if len(rsi) > 0 else 50
        details["RSI"] = round(rsi_val, 2)

        if 40 <= rsi_val <= 65:
            score += 10
            details["RSI信号"] = "RSI顺势区（健康上涨）"
        elif rsi_val < 30:
            score -= 5
            details["RSI信号"] = "RSI超卖（可能拖累）"
        elif rsi_val > 75:
            score -= 10
            details["RSI信号"] = "RSI超买（注意风险）"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 波段主升浪战法：量价维度 ====================

    def _evaluate_volume_price_wave(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        量价维度评估 - 波段主升浪战法

        核心：放量突破 + 量价配合
        """
        score = 50  # 基础分
        details = {}

        try:
            volumes = df['volume'].astype(float).values
            closes = df['close'].astype(float).values

            # 计算各项量价指标
            vol_5avg = np.mean(volumes[-6:-1]) if len(volumes) > 5 else np.mean(volumes[:-1])
            vol_10avg = np.mean(volumes[-11:-1]) if len(volumes) > 10 else vol_5avg
            vol_today = volumes[-1]

            vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1
            vol_10ratio = vol_today / vol_10avg if vol_10avg > 0 else 1

            details["量比"] = round(vol_ratio, 2)
            details["10日量比"] = round(vol_10ratio, 2)

            # 涨跌幅
            if len(closes) >= 2:
                pct_change = (closes[-1] - closes[-2]) / closes[-2] * 100
            else:
                pct_change = 0
            details["涨跌幅"] = round(pct_change, 2)

            # ============ 放量突破信号============

            # 1. 温和放量上涨（最佳启动形态）
            if 1.3 <= vol_ratio <= 3 and pct_change > 0:
                score += 25
                details["放量状态"] = "温和放量上涨（启动确认）"
            # 2. 突破放量
            elif vol_ratio > 3 and pct_change > 3:
                score += 20
                details["放量状态"] = "放量突破（强势启动）"
            # 3. 持续放量
            elif vol_ratio > 2 and vol_10ratio > 1.5:
                score += 15
                details["放量状态"] = "持续放量"
            # 4. 天量
            elif vol_ratio > 5:
                score -= 10
                details["放量状态"] = "天量（警惕见顶）"
            # 5. 缩量上涨
            elif vol_ratio < 0.7 and pct_change > 0:
                score += 5
                details["放量状态"] = "缩量上涨（筹码稳定）"
            # 6. 放量下跌
            elif vol_ratio > 1.5 and pct_change < -2:
                score -= 15
                details["放量状态"] = "放量下跌（主力出货）"
            else:
                details["放量状态"] = "量能正常"

            # ============ 量价配合度 ============
            if vol_ratio > 1.3 and pct_change > 0:
                score += 10
                details["量价配合"] = "量价配合良好"
            elif vol_ratio < 0.7 and pct_change < 0:
                score += 5
                details["量价配合"] = "缩量调整（健康）"
            elif vol_ratio > 1.5 and pct_change < 0:
                details["量价配合"] = "量价背离（警惕）"

        except Exception as e:
            logger.warning(f"量价评估异常: {e}")

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 波段主升浪战法：形态维度 ====================

    def _evaluate_patterns_wave(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        形态维度评估 - 波段主升浪战法

        核心：整理形态完成 + 突破在即
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values
        highs = df['high'].astype(float).values
        lows = df['low'].astype(float).values

        # ============ 突破前高判断 ============
        if len(closes) >= 20:
            high_20 = np.max(highs[-20:-1])  # 前19天最高价（不含今天）
            current_high = highs[-1]
            dist_to_high = (current_high - high_20) / high_20 * 100 if high_20 > 0 else 0

            details["20日最高"] = round(high_20, 2)
            details["距前高"] = f"{dist_to_high:.1f}%"

            # 1. 刚刚突破20日新高
            if current_high > high_20 and dist_to_high < 5:
                score += 25
                details["突破信号"] = "刚刚突破20日新高（启动确认）"
            # 2. 逼近20日新高
            elif dist_to_high > -3 and dist_to_high < 3:
                score += 15
                details["突破信号"] = "逼近20日新高（突破在即）"
            # 3. 已突破一段
            elif dist_to_high > 5:
                score += 5
                details["突破信号"] = "已突破20日新高一段"
            # 4. 远离前期高点
            elif dist_to_high < -10:
                score -= 5
                details["突破信号"] = "仍距前高较远"

        # ============ 整理形态识别 ============
        if len(closes) >= 20:
            # 计算高低点
            high_20 = np.max(highs[-20:])
            low_20 = np.min(lows[-20:])
            range_pct = (high_20 - low_20) / low_20 * 100 if low_20 > 0 else 0

            details["20日振幅"] = f"{range_pct:.1f}%"

            # 1. 窄幅整理（蓄势）
            if range_pct < 10:
                score += 15
                details["整理形态"] = "窄幅整理（蓄势待发）"
            # 2. 中幅整理
            elif range_pct < 20:
                score += 10
                details["整理形态"] = "中幅整理（正常）"
            # 3. 宽幅震荡
            else:
                score -= 5
                details["整理形态"] = "宽幅震荡（方向不明）"

        # ============ K线形态 ============
        if len(closes) >= 5:
            # 最近5天的K线组合
            last_5_closes = closes[-5:]
            last_5_opens = df['open'].astype(float).values[-5:] if 'open' in df.columns else last_5_closes

            # 阳线数量
            bullish_count = sum(1 for i in range(1, 5) if closes[-i] > closes[-i-1])

            if bullish_count >= 4:
                score += 10
                details["K线形态"] = "连续阳线（强势）"
            elif bullish_count >= 3:
                score += 5
                details["K线形态"] = "多数阳线（偏强）"
            else:
                details["K线形态"] = "混合K线"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 波段主升浪战法：位置维度 ====================

    def _evaluate_position_wave(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        位置维度评估 - 波段主升浪战法

        核心：相对低位启动（避免追高）
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values

        # ============ BOLL位置 ============
        boll_period = 20
        if len(closes) >= boll_period:
            recent = closes[-boll_period:]
            mid = np.mean(recent)
            std = np.std(recent)
            upper = mid + 2 * std
            lower = mid - 2 * std
            current = closes[-1]

            boll_pos = (current - lower) / (upper - lower) * 100 if upper > lower else 50
            details["BOLL位置"] = f"{boll_pos:.1f}%"

            # 1. BOLL中轨附近（最佳启动区）
            if 30 <= boll_pos <= 70:
                score += 15
                details["BOLL信号"] = "BOLL中轨附近（启动区）"
            # 2. BOLL上轨（追高风险）
            elif boll_pos > 85:
                score -= 15
                details["BOLL信号"] = "BOLL上轨（追高风险）"
            # 3. BOLL下轨（可能还没启动）
            elif boll_pos < 20:
                score -= 5
                details["BOLL信号"] = "BOLL下轨（弱势）"

        # ============ 相对位置 ============
        if len(closes) >= 60:
            ma60 = np.mean(closes[-60:])
            current = closes[-1]

            if current > ma60:
                score += 10
                details["60日均线"] = "在MA60上方（强势）"
            else:
                details["60日均线"] = "在MA60下方（弱势）"

        # ============ 排除高位追涨 ============
        if len(closes) >= 20:
            change_20d = (closes[-1] - closes[-20]) / closes[-20] * 100
            details["20日涨幅"] = f"{change_20d:.1f}%"

            # 涨幅过大可能是短线顶部
            if change_20d > 40:
                score -= 20
                details["追高风险"] = "20日涨幅过大（警惕）"
            elif change_20d > 25:
                score -= 10
                details["追高风险"] = "20日涨幅较大"
            elif change_20d < -15:
                score -= 5
                details["追高风险"] = "20日跌幅较大（弱势）"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 波段主升浪战法：情绪维度 ====================

    def _evaluate_sentiment_wave(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        情绪维度评估 - 波段主升浪战法

        核心：板块龙头气质 + 题材支撑
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values
        volumes = df['volume'].astype(float).values

        # ============ 涨跌势判断 ============
        if len(closes) >= 5:
            change_5d = (closes[-1] - closes[-5]) / closes[-5] * 100
            details["5日涨幅"] = f"{change_5d:.1f}%"

            # 1. 温和上涨（健康）
            if 5 <= change_5d <= 20:
                score += 15
                details["涨跌势"] = "温和上涨（健康上涨）"
            # 2. 强势上涨
            elif change_5d > 20:
                score += 10
                details["涨跌势"] = "强势上涨（注意回调）"
            # 3. 小幅上涨
            elif change_5d > 0:
                score += 5
                details["涨跌势"] = "小幅上涨"
            # 4. 下跌
            else:
                score -= 10
                details["涨跌势"] = "短期下跌"

        # ============ 成交量活跃度 ============
        if len(volumes) >= 20:
            vol_20avg = np.mean(volumes[-20:])
            vol_5avg = np.mean(volumes[-5:])
            vol_ratio = vol_5avg / vol_20avg if vol_20avg > 0 else 1

            if vol_ratio > 2:
                score += 10
                details["活跃度"] = "成交量放大（资金关注）"
            elif vol_ratio > 1.3:
                score += 5
                details["活跃度"] = "成交量温和放大"
            else:
                details["活跃度"] = "成交量正常"

        # ============ 涨停基因（简化版）============
        if len(closes) >= 10:
            # 检查近期是否有涨停
            pct_changes = np.diff(closes[-10:]) / closes[-10:-1] * 100
            limit_up_days = sum(1 for p in pct_changes if p > 9.5)

            if limit_up_days >= 2:
                score += 15
                details["涨停基因"] = f"10日内涨停{limit_up_days}次（强势）"
            elif limit_up_days == 1:
                score += 10
                details["涨停基因"] = "10日内有涨停"
            else:
                details["涨停基因"] = "无涨停记录"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 波段主升浪战法：突破维度 ====================

    def _evaluate_breakout_wave(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        突破维度评估 - 波段主升浪战法（核心！）

        核心：突破的有效性确认
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values
        volumes = df['volume'].astype(float).values
        highs = df['high'].astype(float).values

        # ============ 突破确认 ============
        if len(closes) >= 20:
            # 20日新高突破
            high_20 = np.max(highs[-20:-1])
            current = closes[-1]

            if current > high_20:
                # 突破成功
                vol_today = volumes[-1]
                vol_5avg = np.mean(volumes[-6:-1])

                if vol_today > vol_5avg * 1.5:
                    score += 25
                    details["突破类型"] = "放量突破20日新高（启动确认）"
                else:
                    score += 10
                    details["突破类型"] = "缩量突破20日新高（需观察）"
            else:
                # 接近前高
                dist = (high_20 - current) / high_20 * 100 if high_20 > 0 else 0
                if dist < 3:
                    score += 15
                    details["突破类型"] = "逼近20日新高（突破在即）"
                else:
                    score -= 5
                    details["突破类型"] = "距20日新高较远"

        # ============ 突破涨幅控制 ============
        if len(closes) >= 5:
            change_5d = (closes[-1] - closes[-5]) / closes[-5] * 100

            # 最佳突破涨幅：3-8%
            if 3 <= change_5d <= 8:
                score += 20
                details["突破强度"] = "完美突破涨幅（启动）"
            elif change_5d > 15:
                score -= 15
                details["突破强度"] = "涨幅过大（可能是短线顶）"
            elif change_5d < 0:
                score -= 10
                details["突破强度"] = "股价反而下跌"

        # ============ 突破量能要求 ============
        if len(volumes) >= 5:
            vol_today = volumes[-1]
            vol_5avg = np.mean(volumes[-6:-1])

            if vol_today > vol_5avg * 2:
                score += 10
                details["突破量能"] = "突破量能充足"
            elif vol_today < vol_5avg * 0.5:
                score -= 5
                details["突破量能"] = "突破量能不足"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 波段启动信号识别 ====================

    def _identify_wave_breakout(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        识别波段启动信号

        满足以下任一条件即为波段启动：
        1. 均线金叉 + MACD金叉（双金叉）
        2. 放量突破前高 + RSI顺势
        3. 连续3天上涨 + 成交量放大
        """
        result = {
            "启动信号": False,
            "信号强度": "无",
            "信号详情": []
        }

        closes = df['close'].astype(float).values
        volumes = df['volume'].astype(float).values

        # 计算指标
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])

        macd, signal, hist = self._calc_macd(closes)
        macd_val = float(macd[-1]) if len(macd) > 0 else 0
        signal_val = float(signal[-1]) if len(signal) > 0 else 0

        rsi = self._calc_rsi(closes)
        rsi_val = float(rsi[-1]) if len(rsi) > 0 else 50

        signals = []

        # ============ 信号1: 双金叉（均线+MACD）============
        if ma5 > ma10 and macd_val > signal_val:
            ma_before = np.mean(closes[-6:-1])
            ma10_before = np.mean(closes[-11:-1])
            macd_before = float(macd[-2]) if len(macd) >= 2 else 0
            signal_before = float(signal[-2]) if len(signal) >= 2 else 0

            if ma5 > ma10_before and macd_val > signal_before:
                signals.append(("双金叉", 40))

        # ============ 信号2: 放量突破 + RSI顺势 ============
        if len(volumes) >= 5:
            vol_today = volumes[-1]
            vol_5avg = np.mean(volumes[-6:-1])
            vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1

            high_20 = np.max(df['high'].astype(float).values[-20:-1])
            if closes[-1] > high_20 and vol_ratio > 1.3 and 40 <= rsi_val <= 70:
                signals.append(("放量突破+RSI顺势", 35))

        # ============ 信号3: 连续上涨 + 量能放大 ============
        if len(closes) >= 4:
            up_days = sum(1 for i in range(1, 4) if closes[-i] > closes[-i-1])
            vol_today = volumes[-1]
            vol_3avg = np.mean(volumes[-4:-1])

            if up_days >= 3 and vol_today > vol_3avg * 1.5:
                signals.append(("连涨+放量", 30))

        # ============ 信号4: MACD红柱放大 + 均线多头 ============
        if len(hist) >= 2:
            hist_now = float(hist[-1])
            hist_before = float(hist[-2])

            if hist_now > 0 and hist_now > hist_before and ma5 > ma10 > ma20:
                signals.append(("MACD红柱放大+多头", 25))

        # ============ 信号5: 突破整理区间 ============
        if len(closes) >= 20:
            high_20 = np.max(df['high'].astype(float).values[-20:])
            low_20 = np.min(df['low'].astype(float).values[-20:])
            range_width = high_20 - low_20

            if range_width > 0:
                position = (closes[-1] - low_20) / range_width
                if position > 0.9:  # 接近区间高点
                    vol_ratio = volumes[-1] / np.mean(volumes[-5:-1]) if len(volumes) > 5 else 1
                    if vol_ratio > 1.2:
                        signals.append(("突破整理高点+放量", 25))

        # ============ 综合评分 ============
        if signals:
            # 取最强信号
            signals.sort(key=lambda x: x[1], reverse=True)
            strongest = signals[0]

            total_score = sum(s[1] for s in signals)

            if strongest[1] >= 35 and total_score >= 60:
                result["启动信号"] = True
                result["信号强度"] = "强烈"
            elif strongest[1] >= 25 and total_score >= 40:
                result["启动信号"] = True
                result["信号强度"] = "中等"
            else:
                result["启动信号"] = True
                result["信号强度"] = "弱"

            result["信号详情"] = [s[0] for s in signals]

        return result

    # ==================== 波段交易信号生成 ====================

    def _generate_wave_signal(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成波段交易信号

        波段核心：买在启动点，持仓到目标位
        """
        composite = result.get("综合", {})
        composite_score = composite.get("评分", 0)
        rating = composite.get("评级", "C")

        wave_signal = result.get("波段信号", {})
        has_breakout = wave_signal.get("启动信号", False)
        breakout_strength = wave_signal.get("信号强度", "无")

        # 获取数据
        df = result.get("_df")
        if df is None:
            return {"操作": "无", "建议": "数据不足"}

        closes = df['close'].astype(float).values
        current_price = closes[-1]

        # ============ 信号判断 ============

        # 1. 强烈启动信号
        if has_breakout and breakout_strength == "强烈" and composite_score >= 65:
            signal = "买入"
            suggestion = "波段启动信号强烈，强烈建议买入"
            action_level = "主攻"

        # 2. 中等启动信号
        elif has_breakout and breakout_strength == "中等" and composite_score >= 60:
            signal = "加仓"
            suggestion = "波段信号确认，可以加仓"
            action_level = "次攻"

        # 3. 弱启动信号
        elif has_breakout and composite_score >= 55:
            signal = "持有/观察"
            suggestion = "有启动迹象，继续观察"
            action_level = "观察"

        # 4. 评分高但无启动信号
        elif composite_score >= 70:
            signal = "持有"
            suggestion = "评分较高但无明确启动信号，等待"
            action_level = "观察"

        # 5. 评分一般
        elif composite_score >= 50:
            signal = "观望"
            suggestion = "评分一般，继续等待机会"
            action_level = "备用"

        # 6. 评分低
        else:
            signal = "不考虑"
            suggestion = "评分较低，不建议参与"
            action_level = "排除"

        # ============ 计算止损止盈 ============
        stop_loss_str, take_profit_str = self._calculate_wave_stops(result)

        # ============ 明日买入条件 ============
        tomorrow_conditions = self._generate_wave_tomorrow_conditions(result)

        return {
            "信号": signal,
            "建议": suggestion,
            "操作": signal,
            "分级": action_level,
            "止损": stop_loss_str,
            "止盈": take_profit_str,
            "理由": result.get("波段信号", {}).get("信号详情", []),
            "仓位建议": self._get_wave_position_suggestion(composite_score, breakout_strength),
            "波段启动": has_breakout,
            "启动强度": breakout_strength,
            "明日买入条件": tomorrow_conditions,
        }

    def _calculate_wave_stops(self, result: Dict[str, Any]) -> Tuple[str, str]:
        """
        计算波段战法的止损止盈

        波段特点：
        - 止损相对紧凑（入场后快速脱离成本区）
        - 止盈相对宽松（让利润奔跑）
        """
        df = result.get("_df")
        if df is None:
            return "8%", "15-20%"

        closes = df['close'].astype(float).values
        current_price = closes[-1]

        # 计算近期低点
        low_10 = np.min(closes[-10:]) if len(closes) >= 10 else current_price

        # ATR计算
        if len(closes) >= 14:
            tr_list = []
            for i in range(1, min(14, len(closes))):
                high = float(df['high'].iloc[-i])
                low = float(df['low'].iloc[-i])
                prev_close = float(df['close'].iloc[-i-1])
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                tr_list.append(tr)
            atr = np.mean(tr_list)
            atr_pct = atr / current_price * 100
        else:
            atr_pct = 3

        # 止损：近期低点下方2-3%或ATR的1.5倍
        stop_distance = min((current_price - low_10) / current_price * 100, atr_pct * 1.5)
        stop_distance = max(stop_distance, 5)  # 最小5%
        stop_distance = min(stop_distance, 10)  # 最大10%
        stop_loss = current_price * (1 - stop_distance / 100)

        # 止盈：目标15-25%（波段行情）
        take_profit_low = current_price * 1.15
        take_profit_high = current_price * 1.25

        # 根据评分调整止盈目标
        composite = result.get("综合", {})
        score = composite.get("评分", 60)
        if score >= 75:
            # 高评分可以期待更大行情
            take_profit_low = current_price * 1.20
            take_profit_high = current_price * 1.30

        stop_loss_str = f"{stop_distance:.1f}%"
        take_profit_str = f"{take_profit_low/current_price*100:.0f}-{take_profit_high/current_price*100:.0f}%"

        return stop_loss_str, take_profit_str

    def _generate_wave_tomorrow_conditions(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成波段战法的明日买入条件
        """
        conditions = {
            "观察要点": [],
            "买入区间": "",
            "不买条件": []
        }

        df = result.get("_df")
        if df is None:
            return conditions

        closes = df['close'].astype(float).values
        current_price = closes[-1]

        # 正常买入区间：开盘价±2%
        buy_low = current_price * 0.98
        buy_high = current_price * 1.02
        conditions["买入区间"] = f"{buy_low:.2f}-{buy_high:.2f}"

        # 观察要点
        wave_signal = result.get("波段信号", {})
        if wave_signal.get("启动信号"):
            conditions["观察要点"].append("确认启动信号是否延续")

        macd = result.get("动量", {}).get("详情", {})
        if macd.get("MACD状态"):
            conditions["观察要点"].append(f"MACD状态: {macd['MACD状态']}")

        vol = result.get("量价", {}).get("详情", {})
        if vol.get("放量状态"):
            conditions["观察要点"].append(f"量能: {vol['放量状态']}")

        # 不买条件
        conditions["不买条件"] = [
            "高开>3%不追（等回调）",
            "跌破今日低点下方3%止损",
            "大盘单边下跌时不加仓"
        ]

        return conditions

    def _get_wave_position_suggestion(self, score: float, breakout_strength: str) -> str:
        """根据评分和启动强度给出仓位建议"""
        if breakout_strength == "强烈" and score >= 70:
            return "正常仓位，单只不超过30%"
        elif breakout_strength == "中等" and score >= 60:
            return "轻仓，单只不超过20%"
        elif breakout_strength == "弱" or score < 60:
            return "观察仓，单只不超过10%"
        else:
            return "标准仓位，单只不超过25%"

    # ==================== 波段主升浪战法：综合评分 ====================

    def _calculate_composite_score_wave(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """计算综合评分 - 波段主升浪战法权重"""
        # 波段战法权重配置
        weights = {
            "趋势": 0.20,    # 均线多头/即将形成
            "动量": 0.25,    # MACD金叉/红柱放大
            "量价": 0.15,    # 放量突破
            "形态": 0.10,    # 整理形态完成
            "位置": 0.05,    # 相对低位
            "情绪": 0.05,    # 板块/题材
            "突破": 0.20,    # 突破有效性（核心！）
        }

        # 计算加权评分
        total_score = 0
        dim_scores = {}

        for dim, weight in weights.items():
            dim_result = result.get(dim, {})
            dim_score = dim_result.get("评分", 50)  # 默认50
            weighted = dim_score * weight
            total_score += weighted
            dim_scores[dim] = dim_score

        # 波段启动信号加成
        wave_signal = result.get("波段信号", {})
        if wave_signal.get("启动信号"):
            strength = wave_signal.get("信号强度", "无")
            if strength == "强烈":
                total_score += 10
            elif strength == "中等":
                total_score += 5

        # 限制评分范围
        total_score = max(0, min(100, total_score))

        # 评级
        if total_score >= 80:
            rating = "A"
            desc = "强势（强烈建议买入）"
        elif total_score >= 70:
            rating = "B+"
            desc = "较好（建议买入）"
        elif total_score >= 60:
            rating = "B"
            desc = "一般（可以关注）"
        elif total_score >= 50:
            rating = "C"
            desc = "较弱（观望）"
        else:
            rating = "D"
            desc = "弱势（不建议）"

        return {
            "评分": round(total_score, 1),
            "评级": rating,
            "描述": desc,
            "各维度": dim_scores,
            "权重": weights
        }

    # ==================== 左侧战法：左侧维度（核心） ====================

    def _evaluate_left_side(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        左侧维度评估 - 核心超跌反弹信号

        这是左侧战法的核心！
        """
        score = 50  # 基础分
        details = {}

        closes = df['close'].astype(float).values
        volumes = df['volume'].astype(float).values

        # ============ 1. RSI超卖信号 ============
        rsi = self._calc_rsi(closes)
        rsi_val = float(rsi[-1]) if len(rsi) > 0 else 50
        details["RSI"] = round(rsi_val, 2)

        if rsi_val < 20:
            score += 30
            details["RSI信号"] = "深度超卖（强烈反弹信号）"
        elif rsi_val < 25:
            score += 25
            details["RSI信号"] = "严重超卖"
        elif rsi_val < 30:
            score += 20
            details["RSI信号"] = "超卖（反弹概率大）"
        elif rsi_val < 40:
            score += 10
            details["RSI信号"] = "偏低"
        else:
            details["RSI信号"] = "正常/偏高"

        # ============ 2. BOLL下轨支撑 ============
        boll_period = 20
        if len(closes) >= boll_period:
            recent = closes[-boll_period:]
            mid = np.mean(recent)
            std = np.std(recent)
            lower = mid - 2 * std
            current = closes[-1]
            boll_pos = (current - lower) / (mid - lower) * 100 if mid > lower else 50
            details["BOLL位置"] = f"{boll_pos:.1f}%"

            if boll_pos < 10:
                score += 25
                details["BOLL信号"] = "BOLL下轨极度超卖（强烈支撑）"
            elif boll_pos < 20:
                score += 20
                details["BOLL信号"] = "BOLL下轨附近（强支撑）"
            elif boll_pos < 35:
                score += 10
                details["BOLL信号"] = "BOLL中下轨"
            else:
                details["BOLL信号"] = "BOLL中上轨"

        # ============ 3. 乖离率（BIAS）- 偏离均线程度 ============
        ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else closes[-1]
        bias = (closes[-1] - ma20) / ma20 * 100
        details["20日乖离率"] = round(bias, 2)

        if bias < -15:
            score += 25
            details["BIAS信号"] = "深度负乖离（强烈反弹信号）"
        elif bias < -12:
            score += 20
            details["BIAS信号"] = "较大负乖离"
        elif bias < -8:
            score += 15
            details["BIAS信号"] = "负乖离"
        elif bias < -5:
            score += 8
            details["BIAS信号"] = "轻度负乖离"
        else:
            details["BIAS信号"] = "正常/正乖离"

        # ============ 4. 缩量止跌信号 - 地量见地价 ============
        vol_5avg = np.mean(volumes[-6:-1]) if len(volumes) > 5 else np.mean(volumes[:-1])
        vol_today = volumes[-1]
        vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1.0
        details["量比"] = round(vol_ratio, 2)

        if vol_ratio < 0.3:
            score += 20
            details["量能信号"] = "极度缩量（地量，见底信号）"
        elif vol_ratio < 0.5:
            score += 15
            details["量能信号"] = "缩量（卖压枯竭）"
        elif vol_ratio < 0.7:
            score += 8
            details["量能信号"] = "轻度缩量"
        elif vol_ratio > 2.0:
            score += 5
            details["量能信号"] = "放量（关注是否有主力介入）"
        else:
            details["量能信号"] = "正常量能"

        # ============ 5. 底部放量异动 - 主力介入信号 ============
        if len(volumes) >= 20:
            vol_20avg = np.mean(volumes[-20:])
            vol_5avg_now = np.mean(volumes[-5:])
            vol_recent_ratio = vol_5avg_now / vol_20avg if vol_20avg > 0 else 1.0
            details["5日量/20日量"] = round(vol_recent_ratio, 2)

            # 底部放量且股价不再创新低
            low_20 = np.min(closes[-20:])
            if vol_recent_ratio > 1.8 and closes[-1] > closes[-10]:  # 放量且股价不再新低
                score += 20
                details["底部异动"] = "底部放量上涨（主力介入！）"
            elif vol_recent_ratio > 1.5 and closes[-1] > closes[-5]:
                score += 12
                details["底部异动"] = "温和放量"
            elif vol_recent_ratio > 1.5:
                score += 5
                details["底部异动"] = "底部量能增加"

        # ============ 6. 前期支撑位测试 ============
        if len(closes) >= 60:
            low_60 = np.min(closes[-60:])
            dist_to_60low = (closes[-1] - low_60) / low_60 * 100
            details["距60日最低"] = f"{dist_to_60low:.1f}%"

            if dist_to_60low < 3:
                score += 15
                details["支撑信号"] = "测试60日最低支撑（反弹临界）"
            elif dist_to_60low < 5:
                score += 8
                details["支撑信号"] = "接近60日最低"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 左侧战法：量价维度 ====================

    def _evaluate_volume_price_left(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        量价维度评估 - 左侧战法

        核心：地量见底，放量反弹
        """
        score = 50  # 基础分
        details = {}

        try:
            volumes = df['volume'].astype(float).values
            closes = df['close'].astype(float).values
            pct_changes = df['pct_change'].astype(float).values if 'pct_change' in df.columns else df['close'].pct_change().values * 100

            # ============ 量比计算 ============
            vol_5avg = np.mean(volumes[-6:-1]) if len(volumes) > 5 else volumes[-1]
            vol_today = volumes[-1]
            vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1

            details["量比"] = round(vol_ratio, 2)

            # ============ 左侧量价信号============

            # 1. 地量见底（卖压枯竭）
            if vol_ratio < 0.3:
                score += 25
                details["量价信号"] = "极度缩量（地量，见底信号）"
            elif vol_ratio < 0.5:
                score += 20
                details["量价信号"] = "缩量止跌"
            elif vol_ratio < 0.7:
                score += 10
                details["量价信号"] = "轻度缩量"
            # 2. 底部放量反弹
            elif vol_ratio > 1.5:
                price_change = pct_changes[-1] if len(pct_changes) > 0 else 0
                if price_change > 0:
                    score += 20
                    details["量价信号"] = "底部放量上涨（主力介入）"
                else:
                    score += 10
                    details["量价信号"] = "放量但股价未涨"

            # ============ 持续缩量判断 ============
            recent_vol = volumes[-5:]
            avg_vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
            all_shrinking = all(v < avg_vol_20 for v in recent_vol)

            if all_shrinking and len(recent_vol) >= 5:
                score += 15
                details["持续缩量"] = "是（卖压持续枯竭）"
            else:
                details["持续缩量"] = "否"

            # ============ 成交量结构变化 ============
            # 今日成交量是否超过5日均量（反弹放量）
            if vol_ratio > 1.2:
                score += 10
                details["放量反弹"] = "是"
            else:
                details["放量反弹"] = "否"

        except Exception as e:
            logger.debug(f"量价评估异常: {e}")
            details["量价信号"] = "评估异常"

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 左侧战法：形态维度 ====================

    def _evaluate_patterns_left(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        形态维度评估 - 左侧战法

        核心：探底形态、锤子线、底部反转信号
        """
        score = 50  # 基础分
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

                # ============ 1. 锤子线（强烈左侧买入信号！）============
                # 特征：下影线是实体的2倍以上，上影线很短
                if lower_shadow > body * 2 and upper_shadow < body * 0.5:
                    details["形态"].append("锤子线")
                    if i == -1:  # 今日
                        score += 25
                        details["今日形态"] = "锤子线（探底回升！）"
                    else:
                        score += 15

                # ============ 2. 早晨之星（左侧反转形态）============
                if i == -3 and len(closes) >= 3:
                    # 第一天大阴线，第二天整理，第三天小阳线
                    body1 = abs(closes[-3] - opens[-3]) / opens[-3]
                    body3 = abs(closes[-1] - opens[-1]) / opens[-1]
                    if body1 > 0.03 and body3 < 0.02:
                        details["形态"].append("早晨之星")
                        if i == -1:
                            score += 20

                # ============ 3. 跳空低开反弹 ============
                if i == -1 and len(closes) >= 2:
                    gap = opens[-1] - closes[-2]
                    if gap < 0 and abs(gap / closes[-2]) > 0.02:
                        score += 20
                        details["形态"].append("向下跳空反转")
                        details["今日形态"] = "低开反弹（强烈信号）"

                # ============ 4. 大阳线反弹 ============
                if c > o and (c - o) / o > 0.03:  # 涨幅大于3%
                    if i == -1:
                        # 今日大阳线
                        if lower_shadow > body * 0.5:  # 同时有下影线
                            score += 20
                            details["今日形态"] = "大阳线+下影线（反弹确立）"
                        else:
                            score += 15
                            details["今日形态"] = "大阳线反弹"

                # ============ 5. 连续下跌后的止跌信号 ============
                if i == -1 and len(pct_changes) >= 5:
                    recent_changes = df['pct_change'].astype(float).values if 'pct_change' in df.columns else df['close'].pct_change().values * 100
                    down_days = sum(1 for c in recent_changes[-5:] if c < -0.5)
                    if down_days >= 3 and (c - closes[-5]) / closes[-5] < -0.1:
                        score += 15
                        details["连续下跌"] = f"连续{down_days}天下跌后止跌"

            # ============ 6. 突破下降趋势线 ============
            if len(closes) >= 10:
                # 简单判断：最近低点抬高
                low_5 = np.min(closes[-5:])
                low_10_before = np.min(closes[-10:-5])
                if low_5 > low_10_before:
                    score += 15
                    details["趋势信号"] = "低点抬高（下降趋势可能逆转）"

        except Exception as e:
            logger.debug(f"形态评估异常: {e}")

        if not details["形态"]:
            details["形态"].append("无明显左侧形态")

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 左侧战法：位置维度 ====================

    def _evaluate_position_left(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        位置维度评估 - 左侧战法

        核心：低位、支撑位、有反弹空间
        """
        score = 50  # 基础分
        details = {}

        try:
            closes = df['close'].astype(float).values
            highs = df['high'].astype(float).values
            lows = df['low'].astype(float).values

            # ============ BOLL位置 ============
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

                # 左侧：位置越低越好
                if position < 15:
                    score += 25
                    details["BOLL信号"] = "BOLL下轨极端低位（强烈支撑）"
                elif position < 25:
                    score += 20
                    details["BOLL信号"] = "BOLL下轨附近（强支撑）"
                elif position < 40:
                    score += 10
                    details["BOLL信号"] = "BOLL中下轨"
                else:
                    score -= 10
                    details["BOLL信号"] = "BOLL中上轨（上涨空间有限）"

            # ============ 相对位置评估 ============
            high_20 = max(highs[-20:])
            low_20 = min(lows[-20:])
            current_price = closes[-1]

            if high_20 > 0:
                high_position = (current_price - low_20) / (high_20 - low_20) * 100
                details["20日高位占比"] = f"{high_position:.1f}%"

                # 左侧：位置越低，反弹空间越大
                if high_position < 20:
                    score += 20
                    details["相对位置"] = "20日低位（反弹空间大）"
                elif high_position < 35:
                    score += 10
                    details["相对位置"] = "20日中下位"
                elif high_position > 80:
                    score -= 15
                    details["相对位置"] = "20日高位（风险较大）"

            # ============ 距近期低点 ============
            if len(closes) >= 20:
                low_20_price = np.min(closes[-20:])
                dist_from_low = (current_price - low_20_price) / low_20_price * 100
                details["距20日最低"] = f"{dist_from_low:.1f}%"

                if dist_from_low < 2:
                    score += 15
                    details["低点信号"] = "接近20日新低（可能测试支撑）"
                elif dist_from_low < 5:
                    score += 8

        except Exception as e:
            logger.debug(f"位置评估异常: {e}")

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 左侧战法：情绪维度 ====================

    def _evaluate_sentiment_left(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        情绪维度评估 - 左侧战法

        核心：涨停基因（之前有过涨停，可能再来）
        """
        score = 50  # 基础分
        details = {}

        try:
            closes = df['close'].astype(float).values
            pct_changes = df['pct_change'].astype(float).values if 'pct_change' in df.columns else df['close'].pct_change().values * 100

            # ============ 涨停基因（左侧重要！）============

            # 10日内有涨停 = 强势股（可能再来）
            limit_up_count = 0
            for pct in pct_changes[-10:]:
                if pct >= 9.5:
                    limit_up_count += 1

            details["10日涨停次数"] = limit_up_count

            # 左侧战法：涨停基因是加分项，不是必须
            if limit_up_count >= 2:
                score += 30
                details["涨停基因"] = "强（主力资金活跃）"
            elif limit_up_count == 1:
                score += 20
                details["涨停基因"] = "有"
            else:
                # 检查接近涨停
                near_limit = sum(1 for pct in pct_changes[-10:] if pct >= 7)
                if near_limit >= 2:
                    score += 15
                    details["涨停基因"] = "接近涨停"
                else:
                    details["涨停基因"] = "无"

            # ============ 近期跌幅（超跌）============

            pct_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) > 5 else 0
            details["5日涨幅"] = f"{pct_5d:.2f}%"

            # 左侧战法：跌幅越大，反弹概率越高
            if pct_5d < -15:
                score += 25
                details["短期强度"] = "深度超跌（强烈反弹信号）"
            elif pct_5d < -10:
                score += 20
                details["短期强度"] = "超跌"
            elif pct_5d < -5:
                score += 12
                details["短期强度"] = "跌幅较大"
            elif pct_5d < -2:
                score += 5
                details["短期强度"] = "小幅下跌"
            elif pct_5d > 10:
                score -= 10  # 涨太多，左侧意义降低
                details["短期强度"] = "大涨后（左侧机会已过）"

            # ============ 连续下跌 ============
            down_days = 0
            for pct in pct_changes[-5:]:
                if pct < 0:
                    down_days += 1

            if down_days >= 4:
                score += 15
                details["连跌"] = f"{down_days}连跌（反弹概率大）"
            elif down_days >= 3:
                score += 8
                details["连跌"] = f"{down_days}连跌"

            # ============ 前期大涨后的回调 ============
            if len(closes) >= 20:
                high_20 = max(closes[:-1])  # 排除今日
                current = closes[-1]
                from_high = (current - high_20) / high_20 * 100 if high_20 > 0 else 0

                details["距20日高点"] = f"{from_high:.1f}%"

                if from_high < -20:
                    score += 15
                    details["回调信号"] = "深度回调（反弹空间大）"
                elif from_high < -15:
                    score += 10

        except Exception as e:
            logger.debug(f"情绪评估异常: {e}")

        score = max(0, min(100, score))
        details["评分"] = score

        return {"评分": score, "详情": details}

    # ==================== 左侧启动信号识别 ====================

    def _identify_left_breakout(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        识别左侧启动信号

        左侧买点特征：
        1. RSI超卖 + BOLL下轨
        2. 均线收敛 + MACD即将金叉
        3. 地量 + 底部放量
        4. 锤子线 + RSI超卖
        """
        result = {"左侧信号": False, "信号强度": "无", "详情": {}, "评分": 0}

        closes = df['close'].astype(float).values
        volumes = df['volume'].astype(float).values

        if len(closes) < 20:
            return result

        # ============ 1. RSI超卖信号 ============
        rsi = self._calc_rsi(closes)
        rsi_val = float(rsi[-1]) if len(rsi) > 0 else 50

        # ============ 2. BOLL下轨信号 ============
        boll_period = 20
        recent = closes[-boll_period:]
        mid = np.mean(recent)
        std = np.std(recent)
        lower = mid - 2 * std
        current = closes[-1]
        boll_pos = (current - lower) / (mid - lower) * 100 if mid > lower else 50

        # ============ 3. 均线收敛信号 ============
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        ma_spread = abs(ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0

        # ============ 4. MACD信号 ============
        macd, signal, hist = self._calc_macd(closes)
        macd_val = float(macd[-1]) if len(macd) > 0 else 0
        signal_val = float(signal[-1]) if len(signal) > 0 else 0

        # ============ 5. 量能信号 ============
        vol_5avg = np.mean(volumes[-6:-1]) if len(volumes) > 5 else volumes[-1]
        vol_today = volumes[-1]
        vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1.0

        # ============ 综合评分 ============
        breakout_score = 0
        signals = []

        # 强左侧信号1: RSI < 25 + BOLL < 15%
        if rsi_val < 25 and boll_pos < 15:
            breakout_score += 40
            signals.append("RSI深度超卖+BOLL下轨")

        # 强左侧信号2: RSI < 30 + 均线收敛
        if rsi_val < 30 and ma_spread < 3:
            breakout_score += 30
            signals.append("RSI超卖+均线蓄势")

        # 强左侧信号3: 地量 + 底部放量
        if vol_ratio < 0.5 and vol_ratio > 0.3:
            breakout_score += 25
            signals.append("地量见底")

        # 强左侧信号4: MACD即将金叉 + 超卖
        if macd_val > signal_val - 0.05 and rsi_val < 35:  # DIF即将上穿DEA
            breakout_score += 30
            signals.append("MACD即将金叉+RSI超卖")

        # 左侧信号5: 连续下跌后放量反弹
        pct_changes = df['pct_change'].astype(float).values if 'pct_change' in df.columns else df['close'].pct_change().values * 100
        down_days = sum(1 for p in pct_changes[-5:] if p < -0.5)
        if down_days >= 3 and vol_ratio > 1.2:
            breakout_score += 25
            signals.append("连续下跌后放量反弹")

        result["详情"]["信号列表"] = signals
        result["评分"] = breakout_score

        if breakout_score >= 70:
            result["左侧信号"] = True
            result["信号强度"] = "强烈"
        elif breakout_score >= 50:
            result["左侧信号"] = True
            result["信号强度"] = "中等"
        elif breakout_score >= 30:
            result["左侧信号"] = True
            result["信号强度"] = "弱"

        return result

    # ==================== 综合评分计算（左侧） ====================

    def _calculate_composite_score_left(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """计算综合评分 - 左侧战法权重"""
        # 左侧战法权重配置
        weights = {
            "趋势": 0.10,    # 均线蓄势
            "动量": 0.20,    # MACD即将转多
            "左侧": 0.25,    # 超跌反弹核心
            "量价": 0.20,    # 地量见底
            "形态": 0.10,    # 探底形态
            "位置": 0.05,    # 低位支撑
            "情绪": 0.10,    # 涨停基因
        }

        total_score = 0
        for dim, weight in weights.items():
            if dim in result:
                dim_score = result[dim].get("评分", 50)
                total_score += dim_score * weight

        composite = round(total_score, 1)

        # 左侧评级
        if composite >= 75:
            rating = "A"
            rating_desc = "左侧强势买点"
        elif composite >= 60:
            rating = "B+"
            rating_desc = "左侧较好买点"
        elif composite >= 50:
            rating = "B"
            rating_desc = "左侧一般买点"
        elif composite >= 35:
            rating = "C"
            rating_desc = "左侧观望"
        else:
            rating = "D"
            rating_desc = "不适合左侧"

        return {
            "评分": composite,
            "评级": rating,
            "描述": rating_desc,
            "权重": weights
        }

    # ==================== 左侧买点有效性判断 ====================

    def _is_left_entry_valid(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        判断左侧买入时机是否有效（李成刚核心）

        李成刚核心思想：买在分歧，卖在一致
        - 排除大涨后的股票（涨停不追）
        - 确认是否真的处于超跌状态
        """
        validation = {
            "有效": True,
            "原因": [],
            "警告": []
        }

        details = result.get("左侧", {}).get("详情", {})
        pct_changes = result.get("左侧", {}).get("详情", {})

        # ============ 1. 检查短期涨幅（李成刚：不追高）============

        # 5日涨幅
        closes = result.get("_df", pd.DataFrame())['close'].astype(float).values if "_df" in result else []
        if len(closes) >= 6:
            pct_5d = (closes[-1] - closes[-6]) / closes[-6] * 100
            validation["5日涨幅"] = round(pct_5d, 2)

            # 5日涨幅超过20%，左侧买点已过（不应该追）
            if pct_5d > 20:
                validation["有效"] = False
                validation["警告"].append("5日涨幅超过20%，买点已过，不应追高")

            # 涨幅超过15%需要谨慎
            elif pct_5d > 15:
                validation["警告"].append(f"5日涨幅{int(pct_5d)}%，已是反弹行情，左侧意义降低")
        else:
            pct_5d = 0

        # ============ 2. 检查RSI是否还处于超卖区域 ============

        rsi = details.get("RSI", 50)
        if rsi > 50:
            validation["有效"] = False
            validation["警告"].append("RSI已回到50以上，反弹可能已完成")
        elif rsi > 40:
            validation["警告"].append("RSI偏高，反弹空间有限")

        # ============ 3. 检查BOLL位置 ============

        boll_pos_str = details.get("BOLL位置", "50%")
        if isinstance(boll_pos_str, str) and "%" in boll_pos_str:
            boll_pos = float(boll_pos_str.replace("%", ""))
        else:
            boll_pos = 50

        if boll_pos > 50:
            validation["有效"] = False
            validation["警告"].append("股价已脱离BOLL下轨，左侧买点已过")
        elif boll_pos > 35:
            validation["警告"].append("BOLL位置偏高，左侧意义降低")

        # ============ 4. 检查量能是否萎缩（地量见底）============

        vol_ratio = details.get("量比", 1.0)
        if vol_ratio > 2.0:
            validation["警告"].append("量比放大，需确认是反弹还是出货")

        # ============ 5. 李成刚核心：涨停不追 ============

        # 检查今日涨幅
        if "_df" in result:
            df = result["_df"]
            if 'pct_change' in df.columns:
                today_change = float(df['pct_change'].iloc[-1])
                validation["今日涨幅"] = today_change
                if today_change > 9.5:  # 接近涨停
                    validation["有效"] = False
                    validation["警告"].append("接近涨停，不符合左侧买入原则（李成刚：涨停是卖出时机）")
                elif today_change > 5:
                    validation["警告"].append(f"今日涨幅{int(today_change)}%，已是右侧行情")

        return validation

    # ==================== 交易信号生成（左侧） ====================

    def _generate_left_signal(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成左侧交易信号

        左侧核心：买在分歧，卖在一致
        """
        composite = result.get("综合", {}).get("评分", 50)
        left_score = result.get("左侧", {}).get("评分", 50)
        rsi_val = result.get("左侧", {}).get("详情", {}).get("RSI", 50)
        left_breakout = result.get("左侧信号", {})
        left_breakout_signal = left_breakout.get("左侧信号", False)
        left_breakout_strength = left_breakout.get("信号强度", "无")

        # ============ 李成刚核心：检查左侧买点是否有效 ============
        entry_validation = self._is_left_entry_valid(result)
        is_valid = entry_validation.get("有效", True)
        entry_warnings = entry_validation.get("警告", [])

        # ============ 操作信号判断 ============
        # 只有在买点有效的情况下才推荐"左侧买入"
        if composite >= 65 and is_valid:
            operation = "左侧买入（明日观察）"
        elif composite >= 65 and not is_valid:
            # 评分够但买点无效，改为观望
            operation = "观望（追高风险）"
        elif composite >= 55:
            if left_score >= 60 and is_valid:
                operation = "左侧买入（明日观察）"
            else:
                operation = "观望"
        elif composite >= 40:
            operation = "观望"
        else:
            operation = "放弃"

        # ============ 左侧理由（李成刚风格）============
        reasons = []
        details = result.get("左侧", {}).get("详情", {})

        # 李成刚核心：超跌反弹信号
        if details.get("RSI信号", "").find("超卖") >= 0:
            reasons.append("RSI超卖")
        if details.get("BOLL信号", "").find("下轨") >= 0:
            reasons.append("BOLL下轨支撑")
        if details.get("BIAS信号", "").find("负乖离") >= 0:
            reasons.append("负乖离大")
        if details.get("量能信号", "").find("缩量") >= 0:
            reasons.append("地量见底")
        if details.get("量能信号", "").find("地量") >= 0:
            reasons.append("卖压枯竭")

        # 李成刚：涨停基因是加分项，但今日涨停不能买
        today_change = entry_validation.get("今日涨幅", 0)
        if today_change > 9.5:
            reasons.append("涨停（不追，等待回调）")
        elif details.get("涨停基因", "无") != "无":
            reasons.append("涨停基因")

        if left_breakout_signal and is_valid:
            reasons.append(f"左侧启动信号({left_breakout_strength})")

        # 如果买点无效，添加警告理由
        if not is_valid:
            for warning in entry_warnings:
                reasons.append(warning)

        if not reasons:
            reasons.append(f"综合评分{int(composite)}分")

        # ============ 获取当前价 ============
        df = result.get("_df")
        current_price = 0
        if df is not None and len(df) > 0:
            current_price = float(df['close'].iloc[-1])

        # ============ 止盈止损 ============
        stop_loss, take_profit = self._calculate_left_stops(result)

        # ============ 出击分级 ============
        if left_breakout_signal and left_breakout_strength == "强烈" and composite >= 65:
            grade = "主攻"
            position_note = "重仓出击，左侧精准买点"
        elif composite >= 60 or (left_breakout_signal and left_breakout_strength == "中等"):
            grade = "次攻"
            position_note = "正常仓位，左侧顺势"
        elif composite >= 55:
            grade = "观察"
            position_note = "轻仓观察，等待确认"
        else:
            grade = "备用"
            position_note = "暂不参与"

        return {
            "操作": operation,
            "分级": grade,
            "仓位建议": position_note,
            "理由": reasons,
            "止损": stop_loss,
            "止盈": take_profit,
            "左侧信号": left_breakout_signal,
            "左侧强度": left_breakout_strength,
            # ============ 明日买入条件（李成刚：盘后选股，次日决策）============
            "明日买入条件": self._generate_tomorrow_conditions(result, current_price, details),
        }

    def _calculate_left_stops(self, result: Dict[str, Any]) -> Tuple[str, str]:
        """
        计算左侧战法的止损止盈

        左侧特点：
        - 止损可以稍宽（因为是抄底）
        - 止盈可以大一些（因为是反弹/反转）
        """
        df = result.get("_df")
        if df is None or len(df) < 20:
            return "8%", "15-20%"

        closes = df['close'].astype(float).values
        lows = df['low'].astype(float).values
        current_price = closes[-1]

        # 左侧止损：参考前期低点
        low_20 = np.min(lows[-20:])
        low_10 = np.min(lows[-10:])

        # 止损：放在近期低点下方3-5%
        candidate_stop = low_10 * 1.03  # 10日最低*1.03
        candidate_stop_20 = low_20 * 1.05  # 20日最低*1.05

        # 选择较高的止损（更保守）
        if candidate_stop > candidate_stop_20:
            stop_price = candidate_stop
        else:
            stop_price = candidate_stop_20

        stop_pct = (current_price - stop_price) / current_price * 100

        # 限制止损范围：5%-12%
        if stop_pct < 5:
            stop_pct = 5.0
            stop_price = current_price * 0.95
        elif stop_pct > 12:
            stop_pct = 12.0
            stop_price = current_price * 0.88

        # 左侧止盈：目标位前期高点
        highs = df['high'].astype(float).values
        high_20 = max(highs[-20:])

        if high_20 > current_price:
            profit_space = (high_20 - current_price) / current_price * 100
            if profit_space < 10:
                # 空间太小，用ATR估算
                atr = np.mean(np.abs(np.diff(closes[-20:])))
                profit_space = atr / current_price * 100 * 2

            take_profit_low = min(profit_space * 0.6, 15)  # 第一止盈
            take_profit_high = min(profit_space * 0.8, 25)  # 第二止盈
            take_profit_str = f"{take_profit_low:.0f}-{take_profit_high:.0f}%"
        else:
            take_profit_str = "15-25%"

        stop_loss_str = f"{stop_pct:.1f}%"

        return stop_loss_str, take_profit_str

    # ==================== 明日买入条件生成（李成刚：盘后选股，次日决策）====================

    def _generate_tomorrow_conditions(self, result: Dict[str, Any], current_price: float, details: Dict) -> Dict[str, Any]:
        """
        生成明日买入条件（李成刚核心）

        核心思想：今天选出的股票是"明日有机会"，不是"今天就能买"
        明天需要等待信号出现才能买
        """
        conditions = {
            "买入区间": "",
            "触发条件": [],
            "观察要点": [],
            "不买条件": [],
            "风险提示": ""
        }

        df = result.get("_df")
        if df is None or len(df) < 20:
            conditions["买入区间"] = "数据不足"
            return conditions

        closes = df['close'].astype(float).values
        lows = df['low'].astype(float).values
        volumes = df['volume'].astype(float).values

        current_price = closes[-1]

        # ============ 1. 计算明日买入区间 ============
        # 参考近期低点，加上合理范围
        low_20 = np.min(lows[-20:])
        low_10 = np.min(lows[-10:])
        low_5 = np.min(lows[-5:])

        # 理想买入价：在今日最低价附近（-3%~+2%）
        ideal_buy_low = low_5 * 0.97  # 今日最低价下方3%
        ideal_buy_high = low_5 * 1.02  # 今日最低价上方2%

        # 如果low_5太高，用更保守的估算
        if ideal_buy_low > current_price * 0.95:
            ideal_buy_low = current_price * 0.93  # 当前价下方7%
            ideal_buy_high = current_price * 0.99  # 当前价下方1%

        conditions["买入区间"] = f"{ideal_buy_low:.2f}-{ideal_buy_high:.2f}"

        # ============ 2. 触发条件（李成刚：等待信号出现）============

        triggers = []

        # 触发条件1：缩量回调到支撑位
        vol_5avg = np.mean(volumes[-6:-1]) if len(volumes) > 5 else np.mean(volumes[:-1])
        vol_today = volumes[-1]
        vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1.0

        if vol_ratio < 0.7:
            triggers.append("缩量回调到支撑位时买入")

        # 触发条件2：RSI创出新低后反弹
        rsi = details.get("RSI", 50)
        if rsi < 35:
            triggers.append("RSI创出新低后，小幅反弹时买入")

        # 触发条件3：股价创新低但立即拉回
        if closes[-1] <= low_10 * 1.02:
            triggers.append("股价创新低后迅速拉回，形成锤子线时买入")

        # 触发条件4：等待大盘确认
        triggers.append("等待大盘企稳确认")

        conditions["触发条件"] = triggers

        # ============ 3. 观察要点（李成刚：盘中观察）============

        observations = []

        # 观察1：开盘情况
        observations.append("观察开盘情况：低开幅度过大不追，等反弹")

        # 观察2：量能变化
        observations.append(f"当前量比{vol_ratio:.1f}，明日需要观察量能是否萎缩到0.5以下")

        # 观察3：分时均线
        observations.append("观察是否能在分时均线附近企稳")

        # 观察4：大盘配合
        observations.append("观察大盘是否配合，大盘跌时不加仓")

        conditions["观察要点"] = observations

        # ============ 4. 不买条件（李成刚：果断放弃）============

        no_buy = []

        # 不买1：继续放量下跌
        no_buy.append("继续放量下跌（量比>1.5）")

        # 不买2：跌破关键支撑
        if low_10 > 0:
            stop_line = low_10 * 0.95
            no_buy.append(f"跌破{stop_line:.2f}（今日低点下方5%）")

        # 不买3：RSI持续低迷
        if rsi < 30:
            no_buy.append("RSI持续低于20，可能还有新低")

        # 不买4：大盘单边下跌
        no_buy.append("大盘单边下跌时不进场")

        # 不买5：单只仓位限制
        no_buy.append("单只仓位不超过20%")

        conditions["不买条件"] = no_buy

        # ============ 5. 风险提示 ============

        risk = ""
        pct_5d = details.get("5日涨幅", "0%")
        if isinstance(pct_5d, str):
            pct_5d = float(pct_5d.replace("%", ""))

        if pct_5d < -20:
            risk = "跌幅较大，可能还有惯性下跌，建议仓位减半"
        elif pct_5d < -10:
            risk = "跌幅较大，注意控制仓位"

        conditions["风险提示"] = risk

        return conditions

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
