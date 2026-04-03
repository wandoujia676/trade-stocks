"""
选股引擎 - 基于书籍理论的量化选股规则
支持多因素评分模型
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
import numpy as np

from config import SCREENER_DEFAULTS, SECTOR_MAP
from data_fetcher import get_fetcher
from warfare import get_warfare

logger = logging.getLogger(__name__)


class StockScreener:
    """
    智能选股引擎

    选股逻辑基于以下书籍理论：
    - 《短线操盘》：强势股、题材热点、缺口理论
    - 《股市扫地僧》：科学选股、只做强势股
    - 《交易真相》：概率思维、趋势跟随
    - 《量学》：量柱理论、黄金柱
    """

    def __init__(self, params: Dict[str, Any] = None):
        self.params = {**SCREENER_DEFAULTS, **(params or {})}
        self.fetcher = get_fetcher()

    def screen(self, market: str = "全市场", limit: int = 20) -> List[Dict[str, Any]]:
        """
        执行选股筛选

        Args:
            market: 市场范围 (全市场/创业板/科创板/主板)
            limit: 返回数量限制

        Returns:
            筛选后的股票列表，按评分排序
        """
        logger.info(f"开始选股，市场: {market}, 限制: {limit}")

        # 步骤1: 获取候选股票池
        candidates = self._get_candidate_pool(market)
        if not candidates:
            logger.warning("候选股票池为空")
            return []

        logger.info(f"候选股票数量: {len(candidates)}")

        # 步骤2: 批量技术面筛选
        tech_passed = self._filter_technical(candidates)
        logger.info(f"技术面通过数量: {len(tech_passed)}")

        # 步骤3: 基本面筛选
        fund_passed = self._filter_fundamental(tech_passed)
        logger.info(f"基本面通过数量: {len(fund_passed)}")

        # 步骤4: 情绪面筛选
        sentiment_passed = self._filter_sentiment(fund_passed)
        logger.info(f"情绪面通过数量: {len(sentiment_passed)}")

        # 步骤5: 多因素评分
        scored = self._score_stocks(sentiment_passed)

        # 步骤6: 只保留加仓/买入信号（过滤减仓/观望）
        # 使用包含判断，因为信号可能是"持有/加仓"混合信号
        scored = [s for s in scored if "加仓" in s.get("信号", "") or "买入" in s.get("信号", "") or "强烈推荐" in s.get("信号", "")]

        # 排序并返回
        scored.sort(key=lambda x: x["总分"], reverse=True)
        return scored[:limit]

    def _get_candidate_pool(self, market: str) -> List[str]:
        """
        获取候选股票池
        从 monthly_watchlist.txt 读取上月度候选股票（约100只）
        """
        # 尝试从 monthly_watchlist.txt 读取
        base_dir = Path(__file__).parent
        monthly_file = base_dir / "View Results" / "monthly_watchlist.txt"

        codes = []

        if monthly_file.exists():
            try:
                with open(monthly_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # 匹配格式: "代码 - 名称 | 行业 | 评分:xx" 或 "代码 - 名称"
                        if line and not line.startswith("=") and not line.startswith("共") and not line.startswith("月度"):
                            parts = line.split(" - ")
                            if len(parts) >= 1:
                                code = parts[0].strip()
                                # 过滤非股票代码行
                                if code and code.isdigit() and len(code) == 6:
                                    codes.append(code)
                logger.info(f"从 monthly_watchlist.txt 读取到 {len(codes)} 只股票")
            except Exception as e:
                logger.warning(f"读取 monthly_watchlist.txt 失败: {e}")

        # 如果读取失败或文件不存在，使用 fallback 候选池
        if not codes:
            logger.warning("使用 fallback 候选池")
            codes = [
                # 银行
                "000001", "600016", "600036", "601166", "601288", "601328", "601398", "601818",
                # 证券
                "600030", "600837", "601066", "601211", "601688", "000776",
                # 保险
                "601318", "601601", "601628", "601336",
                # 白酒
                "000568", "000858", "600519", "603288",
                # 新能源
                "300750", "002594", "600438", "601012", "002466",
                # 科技龙头
                "000001", "000002", "000063", "000100", "002230", "002241",
                "002415", "002460", "300033", "300059", "300124",
                # 医药
                "000538", "600276", "603259", "300015", "002007",
                # 芯片/半导体
                "002371", "688981", "603501", "002236",
                # 消费电子
                "000725", "002241", "300866",
                # 互联网
                "300059", "300024", "603259",
            ]

        # 根据市场筛选
        if market == "创业板":
            return [c for c in codes if c.startswith("300") and not c.startswith("688")]
        elif market == "科创板":
            return [c for c in codes if c.startswith("688")]
        elif market == "主板":
            return [c for c in codes if c.startswith(("600", "000", "001"))]
        else:  # 全市场
            return list(set(codes))  # 去重

    def _filter_technical(self, codes: List[str]) -> List[Dict[str, Any]]:
        """
        技术面筛选 - 优化版：让更多高动量股票通过

        修改：
        1. 放宽均线要求，不再硬性要求均线多头
        2. 降低成交量门槛
        3. 重点关注近期有涨幅的股票
        """
        passed = []
        ma_params = self.params

        print(f"\n技术面筛选进度（{len(codes)}只）...")

        for i, code in enumerate(codes):
            try:
                df = self.fetcher.get_daily(code)
                if df is None or len(df) < 30:
                    continue

                # 转换为方便计算的格式
                df = df.tail(60).copy()  # 取近60天
                closes = df['close'].astype(float).values
                volumes = df['volume'].astype(float).values

                # ========== 计算各项指标 ==========
                # 均线
                ma5 = self._ma(closes, 5)
                ma10 = self._ma(closes, 10)
                ma20 = self._ma(closes, 20)

                # 5日涨幅（重点！）
                change_5d = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0

                # 10日涨幅
                change_10d = (closes[-1] - closes[-10]) / closes[-10] * 100 if len(closes) >= 10 else change_5d * 2

                # 量比
                vol_ratio = self._volume_ratio(volumes)

                # 平均成交量
                avg_vol = np.mean(volumes[-5:])
                avg_vol_20 = np.mean(volumes[-20:])

                # MACD
                macd, signal, hist = self._macd(closes)

                # ========== 筛选条件（大幅放宽）============

                # 条件1：成交量门槛（降低到5日均量>50万）
                if avg_vol < 50000:  # 50万
                    continue

                # 条件2：排除极度弱势（MACD在-2以下且均线空头）
                macd_val = macd[-1] if len(macd) > 0 else 0
                is_below_ma20 = closes[-1] < ma20[-1] if len(ma20) > 0 else False
                if macd_val < -2 and is_below_ma20:
                    continue

                # 条件3：排除长期下跌的股票（20日跌幅>30%）
                change_20d = (closes[-1] - closes[-20]) / closes[-20] * 100 if len(closes) >= 20 else 0
                if change_20d < -30:
                    continue

                # ========== 通过筛选，计算初步评分 ==========
                # 用于排序的初步评分
                pre_score = 0

                # 近期涨幅加分（重点！）
                if change_5d >= 10:
                    pre_score += 30
                elif change_5d >= 5:
                    pre_score += 20
                elif change_5d >= 0:
                    pre_score += 10

                # 量比加分
                if vol_ratio >= 2.0:
                    pre_score += 15
                elif vol_ratio >= 1.5:
                    pre_score += 10
                elif vol_ratio >= 1.0:
                    pre_score += 5

                # 均线加分
                if len(ma5) > 0 and closes[-1] > ma5[-1]:
                    pre_score += 5
                if len(ma10) > 0 and closes[-1] > ma10[-1]:
                    pre_score += 5
                if len(ma20) > 0 and closes[-1] > ma20[-1]:
                    pre_score += 5

                # MACD加分
                if macd_val > 0:
                    pre_score += 10
                elif macd_val > -1:
                    pre_score += 5

                passed.append({
                    "code": code,
                    "data": df,
                    "metrics": {
                        "5日涨幅": round(change_5d, 2),
                        "10日涨幅": round(change_10d, 2),
                        "量比": round(vol_ratio, 2),
                        "pre_score": pre_score,
                    }
                })

                # 每10只显示进度
                if (i + 1) % 10 == 0:
                    print(f"  已处理 {i+1}/{len(codes)}，通过 {len(passed)} 只")

            except Exception as e:
                logger.debug(f"技术面筛选 {code} 失败: {e}")
                continue

        print(f"  技术面筛选完成：通过 {len(passed)} 只")
        return passed

    def _filter_fundamental(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        基本面筛选 - 优化版：放宽条件，让更多股票通过

        修改：
        1. 大幅降低最小市值门槛（从50亿降到10亿）
        2. 移除价格上限限制（让高价格的好股票也能通过）
        3. 无法获取数据时默认通过
        """
        min_market_cap = self.params.get("市值_min", 10)  # 亿，降低到10亿

        passed = []
        for item in candidates:
            try:
                info = self.fetcher.get_stock_info(item["code"])
                if not info:
                    # 无法获取信息时，默认通过
                    passed.append(item)
                    continue

                # 市值检查（如果有数据）
                if "总市值" in info:
                    market_cap_str = info["总市值"]
                    if "亿" in market_cap_str:
                        cap = float(market_cap_str.replace("亿", "").replace("万", ""))
                        if cap < min_market_cap:
                            continue

                passed.append(item)
            except Exception:
                # 出错时也默认通过
                passed.append(item)
                continue

        return passed

    def _filter_sentiment(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """情绪面筛选"""
        passed = []

        for item in candidates:
            try:
                df = item["data"]
                if df is None or len(df) < 10:
                    continue

                # 检查近期是否有涨停
                pct_changes = df['pct_change'].astype(float).tail(10)
                has_recent_limit_up = (pct_changes >= 9.5).any()

                # 检查是否在近期高点附近
                recent_high = df['high'].astype(float).tail(20).max()
                current_price = df['close'].astype(float).iloc[-1]
                near_high_ratio = current_price / recent_high

                # 情绪面通过条件：近期有涨停 OR 接近近期高点
                if has_recent_limit_up or near_high_ratio > 0.85:
                    item["metrics"]["情绪信号"] = "强" if has_recent_limit_up else "中"
                    passed.append(item)
                elif near_high_ratio > 0.75:
                    item["metrics"]["情绪信号"] = "弱"
                    passed.append(item)

            except Exception as e:
                logger.debug(f"情绪面筛选 {item['code']} 失败: {e}")
                continue

        return passed

    def _score_stocks(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        多因素评分（使用综合战法 + 动量加权）

        优化：加入动量加权，让近期涨幅大的股票更容易被选出
        """
        warfare = get_warfare()

        scored = []
        for item in candidates:
            try:
                df = item["data"]
                if df is None:
                    continue

                # 使用综合战法评估
                warfare_result = warfare.evaluate(df)

                if "error" in warfare_result:
                    continue

                composite = warfare_result.get("综合", {})
                signal = warfare_result.get("信号", {})

                # 基础综合评分
                base_score = composite.get("评分", 50)

                # ========== 动量加权 ==========
                # 获取预筛选阶段的动量评分
                pre_score = item.get("metrics", {}).get("pre_score", 0)
                change_5d = item.get("metrics", {}).get("5日涨幅", 0)

                # 动量加成：近期涨幅大的股票加权
                # 5日涨幅超过10%额外加10-20分
                momentum_bonus = 0
                if change_5d >= 15:
                    momentum_bonus = 20
                elif change_5d >= 10:
                    momentum_bonus = 15
                elif change_5d >= 5:
                    momentum_bonus = 10
                elif change_5d >= 3:
                    momentum_bonus = 5

                # 最终评分 = 基础评分 + 动量加成
                final_score = base_score + momentum_bonus

                # 提取战法各维度评分
                item["总分"] = final_score
                item["基础分"] = base_score
                item["动量加成"] = momentum_bonus
                item["评级"] = composite.get("评级", "B")
                item["趋势分"] = warfare_result.get("趋势", {}).get("评分", 50)
                item["动量分"] = warfare_result.get("动量", {}).get("评分", 50)
                item["量价分"] = warfare_result.get("量价", {}).get("评分", 50)
                item["形态分"] = warfare_result.get("形态", {}).get("评分", 50)
                item["位置分"] = warfare_result.get("位置", {}).get("评分", 50)
                item["情绪分"] = warfare_result.get("情绪", {}).get("评分", 50)

                # 信号
                item["信号"] = signal.get("操作", "持有")
                item["理由"] = signal.get("理由", [])
                item["止损"] = signal.get("止损", "5%")
                item["止盈"] = signal.get("止盈", "15%")

                # 止盈止损动态依据
                if signal.get("止盈止损依据"):
                    item["止盈止损依据"] = signal.get("止盈止损依据")

                # 提取最新价格
                item["最新价"] = float(df['close'].iloc[-1])
                item["涨跌幅"] = float(df['pct_change'].iloc[-1]) if 'pct_change' in df.columns else 0

                scored.append(item)

            except Exception as e:
                logger.debug(f"评分 {item.get('code')} 失败: {e}")
                continue

        return scored

    def _calc_tech_score(self, df: pd.DataFrame) -> float:
        """技术面评分 (0-100)"""
        score = 50.0

        try:
            closes = df['close'].astype(float).values
            volumes = df['volume'].astype(float).values

            # 均线多头程度
            ma5 = self._ma(closes, 5)
            ma10 = self._ma(closes, 10)
            ma20 = self._ma(closes, 20)

            if ma5[-1] > ma10[-1] > ma20[-1]:
                score += 15
            elif ma5[-1] > ma10[-1]:
                score += 8

            # MACD强势
            macd, signal, hist = self._macd(closes)
            if macd[-1] > 0 and hist[-1] > 0:
                score += 15
            elif macd[-1] > 0:
                score += 8

            # 成交量活跃度
            vol_ratio = self._volume_ratio(volumes)
            if vol_ratio > 2:
                score += 10
            elif vol_ratio > 1.5:
                score += 5

            # 趋势强度（相对位置）
            high20 = df['high'].astype(float).tail(20).max()
            low20 = df['low'].astype(float).tail(20).min()
            if high20 > 0:
                price_pos = (closes[-1] - low20) / (high20 - low20)
                score += price_pos * 10

            # 近期涨幅
            pct_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) > 5 else 0
            if 3 < pct_5d < 15:
                score += 10  # 适度涨幅

        except Exception:
            pass

        return min(100, max(0, score))

    def _calc_fund_score(self, item: Dict[str, Any]) -> float:
        """基本面评分 (0-100)"""
        # 简化评分：使用情绪信号和其他可用信息
        score = 60.0

        metrics = item.get("metrics", {})
        turnover_rate = metrics.get("换手率", 0)

        # 高换手率往往意味着活跃
        if turnover_rate > 5:
            score += 15
        elif turnover_rate > 3:
            score += 8

        # 情绪信号
        sentiment = metrics.get("情绪信号", "弱")
        if sentiment == "强":
            score += 25
        elif sentiment == "中":
            score += 15

        return min(100, max(0, score))

    def _calc_sentiment_score(self, item: Dict[str, Any]) -> float:
        """情绪面评分 (0-100)"""
        score = 50.0

        metrics = item.get("metrics", {})
        情绪 = metrics.get("情绪信号", "弱")

        if 情绪 == "强":
            score = 90.0
        elif 情绪 == "中":
            score = 70.0

        return min(100, max(0, score))

    # ==================== 技术指标计算 ====================

    def _ma(self, prices: np.ndarray, period: int) -> np.ndarray:
        """计算移动平均线"""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        return np.convolve(prices, np.ones(period)/period, mode='valid')

    def _macd(self, prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算MACD"""
        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)
        macd = ema_fast - ema_slow
        signal_line = self._ema(macd, signal)
        histogram = macd - signal_line
        return macd, signal_line, histogram

    def _ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """计算指数移动平均"""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        alpha = 2 / (period + 1)
        ema = np.zeros_like(prices)
        ema[0] = prices[0]
        for i in range(1, len(prices)):
            ema[i] = alpha * prices[i] + (1 - alpha) * ema[i-1]
        return ema

    def _volume_ratio(self, volumes: np.ndarray) -> float:
        """计算量比（今日量/5日均量）"""
        if len(volumes) < 6:
            return 1.0
        today_vol = volumes[-1]
        avg_vol_5 = np.mean(volumes[-6:-1])
        return today_vol / avg_vol_5 if avg_vol_5 > 0 else 1.0

    def _has_limit_up(self, df: pd.DataFrame, days: int = 10) -> bool:
        """检查近N日是否有涨停"""
        try:
            pct = df['pct_change'].astype(float).tail(days)
            return (pct >= 9.5).any()
        except:
            return False


# 单例
_screener_instance = None

def get_screener(params: Dict[str, Any] = None) -> StockScreener:
    """获取选股器单例"""
    global _screener_instance
    if _screener_instance is None or params:
        _screener_instance = StockScreener(params)
    return _screener_instance
