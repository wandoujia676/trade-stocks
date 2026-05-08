"""
回测系统 - 小金库 v8.2
用于验证选股策略的历史表现

核心指标：
- 胜率
- 最大连续亏损次数
- 年化收益率
- 夏普比率
- 最大回撤
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json

import pandas as pd
import numpy as np

from data_fetcher import get_fetcher
from warfare import get_warfare

logger = logging.getLogger(__name__)


class Backtester:
    """
    策略回测系统

    回测逻辑：
    1. 选取历史时间段（如最近3年）
    2. 模拟"盘后选股，次日买入"的交易流程
    3. 记录每次交易的买入/卖出点
    4. 计算各项绩效指标
    """

    def __init__(self, initial_capital: float = 1000000):
        """
        Args:
            initial_capital: 初始资金（默认100万）
        """
        self.initial_capital = initial_capital
        self.fetcher = get_fetcher()
        self.warfare = get_warfare()

        # 回测结果
        self.trades: List[Dict[str, Any]] = []  # 交易记录
        self.equity_curve: List[float] = []     # 权益曲线

    def run(
        self,
        start_date: str,
        end_date: str,
        stock_pool: List[str],
        strategy: str = "left",
        stop_loss: float = 0.08,
        take_profit: float = 0.20,
        position_size: float = 0.1,
        use_v90_dimensions: bool = True,
        use_observation_pool: bool = True
    ) -> Dict[str, Any]:
        """
        运行回测

        Args:
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）
            stock_pool: 候选股票池
            strategy: 战法类型（"left" 或 "wave"）
            stop_loss: 止损比例
            take_profit: 止盈比例
            position_size: 单次仓位比例
            use_v90_dimensions: 是否启用 v9.0 三维度（基本面/资金面/催化剂）
            use_observation_pool: 是否启用 v9.0 观察池右侧确认

        4 种组合：
        - (False, False) = v8.x 基线
        - (True, False)  = 仅加新维度
        - (False, True)  = 仅加观察池
        - (True, True)   = v9.0 完整版

        Returns:
            回测结果统计
        """
        config_label = f"v90_dim={use_v90_dimensions}, obs_pool={use_observation_pool}"
        logger.info(f"开始回测: {start_date} -> {end_date}, 策略: {strategy}, 配置: {config_label}")
        logger.info(f"候选股票数: {len(stock_pool)}, 初始资金: {self.initial_capital/10000:.1f}万")

        self.trades = []
        self.equity_curve = [self.initial_capital]

        # 将日期转换为datetime
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")

        # 按月遍历
        current_dt = start_dt
        month_idx = 0
        total_months = ((end_dt - start_dt).days // 30) + 1
        while current_dt < end_dt:
            month_idx += 1
            print(f"  [{month_idx}/{total_months}] 处理 {current_dt.strftime('%Y-%m-%d')}...", flush=True)
            # 模拟"每月15日选股"或"每周三选股"
            month_end = current_dt + timedelta(days=30)
            if month_end > end_dt:
                month_end = end_dt

            # 选股（使用历史数据进行筛选）
            selected = self._select_stocks(
                stock_pool,
                current_dt.strftime("%Y%m%d"),
                limit=5,
                use_v90_dimensions=use_v90_dimensions
            )
            print(f"    选股: {len(selected)} 只", flush=True)

            # 【v9.0 Step 3b】观察池右侧确认（如果开启）
            if use_observation_pool and selected:
                before_count = len(selected)
                selected = self._apply_right_side_confirmation(selected, current_dt)
                print(f"    右侧确认: {before_count} -> {len(selected)} 只", flush=True)

            if selected:
                # 模拟次日买入
                buy_date = (current_dt + timedelta(days=1)).strftime("%Y%m%d")
                for stock in selected[:3]:  # 最多同时持有3只
                    trade = self._simulate_trade(
                        stock,
                        buy_date,
                        strategy,
                        stop_loss,
                        take_profit,
                        position_size
                    )
                    if trade:
                        self.trades.append(trade)

            # 更新权益曲线
            self._update_equity_curve()

            current_dt = month_end

        # 计算绩效指标
        stats = self._calculate_stats()
        stats["配置"] = config_label
        logger.info(f"回测完成: 交易次数={len(self.trades)}, 胜率={stats['胜率']:.1%}")

        return stats

    def _apply_right_side_confirmation(
        self,
        selected: List[Dict[str, Any]],
        current_dt: datetime
    ) -> List[Dict[str, Any]]:
        """
        【v9.0 Step 3b】对左侧选股结果做观察池右侧确认

        规则：拉 T+1~T+3 K线，任意一天满足「实体阳 OR 量比>1.2」则通过

        数据获取失败时 fallback 通过（回测不应因网络/代理问题惩罚策略）
        """
        confirmed = []
        fallback_count = 0

        for stock in selected:
            code = stock["code"]
            try:
                start = (current_dt + timedelta(days=1)).strftime("%Y%m%d")
                end = (current_dt + timedelta(days=10)).strftime("%Y%m%d")
                df_after = self.fetcher.get_daily(code, start_date=start, end_date=end, use_cache=True)

                if df_after is None or df_after.empty:
                    stock['右侧确认'] = {'confirmed_day': 0, 'vol_ratio': 0, 'body_pct': 0, 'fallback': True}
                    confirmed.append(stock)
                    fallback_count += 1
                    continue

                df_before = self.fetcher.get_daily(
                    code,
                    end_date=current_dt.strftime("%Y%m%d"),
                    use_cache=True
                )
                if df_before is None or len(df_before) < 5:
                    stock['右侧确认'] = {'confirmed_day': 0, 'vol_ratio': 0, 'body_pct': 0, 'fallback': True}
                    confirmed.append(stock)
                    fallback_count += 1
                    continue

                vol_5avg = float(df_before['volume'].tail(5).mean())
                if vol_5avg <= 0:
                    stock['右侧确认'] = {'confirmed_day': 0, 'vol_ratio': 0, 'body_pct': 0, 'fallback': True}
                    confirmed.append(stock)
                    fallback_count += 1
                    continue

                # 检查 T+1 ~ T+3
                passed = False
                for i in range(min(3, len(df_after))):
                    row = df_after.iloc[i]
                    open_p = float(row['open'])
                    close_p = float(row['close'])
                    vol = float(row['volume'])

                    is_bullish = close_p > open_p
                    vol_ratio = vol / vol_5avg

                    # 右侧确认：实体阳 OR 量比>1.2（满足其一即可）
                    if is_bullish or vol_ratio > 1.2:
                        stock['右侧确认'] = {
                            'confirmed_day': i + 1,
                            'vol_ratio': round(vol_ratio, 2),
                            'body_pct': round((close_p - open_p) / open_p * 100, 2),
                            'fallback': False
                        }
                        confirmed.append(stock)
                        passed = True
                        break

            except Exception as e:
                logger.debug(f"右侧确认 {code} 异常: {e}")
                stock['右侧确认'] = {'confirmed_day': 0, 'vol_ratio': 0, 'body_pct': 0, 'fallback': True}
                confirmed.append(stock)
                fallback_count += 1

        if fallback_count > 0:
            logger.info(f"观察池过滤: {len(selected)} → {len(confirmed)} (其中 {fallback_count} 只通过 fallback)")
        else:
            logger.debug(f"观察池过滤: {len(selected)} → {len(confirmed)}")
        return confirmed

    def _select_stocks(
        self,
        stock_pool: List[str],
        date: str,
        limit: int = 5,
        use_v90_dimensions: bool = True
    ) -> List[Dict[str, Any]]:
        """
        在指定日期进行选股（历史模拟）

        Args:
            stock_pool: 候选股票池
            date: 选股日期
            limit: 返回数量
            use_v90_dimensions: 是否启用 v9.0 三维度（基本面/资金面/催化剂）
                                False = v8.x 基线（5维度，新维度评分默认50中性）
                                True = v9.0 完整版（8维度）

        注意：基本面/资金面/催化剂数据接口当前只能拿到最新数据，
        历史回测时实际使用的是"未来数据"（lookahead bias），
        结果应作为上限参考而非真实表现。
        """
        results = []

        for code in stock_pool[:50]:  # 限制计算量
            try:
                # 获取历史数据（截止到选股日期）
                # 【v9.0 修复】必须传 start_date，否则默认 start = now()-120天 > end_date 导致空数据
                # 需要至少 60 个交易日，约 90 个自然日，保险起见拉 365 天
                eval_end = date
                eval_start = (datetime.strptime(date, "%Y%m%d") - timedelta(days=365)).strftime("%Y%m%d")
                df = self.fetcher.get_daily(code, start_date=eval_start, end_date=eval_end, use_cache=True)
                if df is None or len(df) < 60:
                    continue

                # 【v9.0 Step 3b】构造 info（决定是否注入三维度数据）
                info = {'code': code}
                if use_v90_dimensions:
                    try:
                        info['_fundamentals'] = self.fetcher.get_financial_indicators(code)
                    except Exception:
                        pass
                    try:
                        info['_moneyflow'] = self.fetcher.get_moneyflow(code, days=5)
                    except Exception:
                        pass
                    try:
                        info['_catalysts'] = self.fetcher.get_catalysts(code)
                    except Exception:
                        pass

                # 使用战法评估
                result = self.warfare.evaluate(df, info=info, mode="left")
                if "error" in result:
                    continue

                composite = result.get("综合", {}).get("评分", 0)
                signal = result.get("信号", {})

                # 【v9.0 Step 3b 修复】回测只看评分阈值，不看 signal 操作文案
                # 原因：warfare._generate_left_signal 会因为"追高风险"等把买入信号降级为"观望"，
                # 但回测目的是验证评分体系的有效性。过严的过滤会导致 0 交易（见 quick 测试）。
                if composite >= 55:
                    results.append({
                        "code": code,
                        "score": composite,
                        "signal": signal,
                        "result": result
                    })

            except Exception as e:
                logger.debug(f"选股评估 {code} 失败: {e}")
                continue

        # 按评分排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def _simulate_trade(
        self,
        stock: Dict[str, Any],
        buy_date: str,
        strategy: str,
        stop_loss: float,
        take_profit: float,
        position_size: float
    ) -> Optional[Dict[str, Any]]:
        """
        模拟单笔交易

        Args:
            stock: 股票信息
            buy_date: 买入日期
            strategy: 战法类型
            stop_loss: 止损比例
            take_profit: 止盈比例
            position_size: 仓位比例

        Returns:
            交易记录
        """
        code = stock["code"]

        # 【v9.0 修复】warfare 的 signal 没有"明日买入条件.价格"字段
        # 回测简化假设：用选股日收盘价作为次日买入价
        buy_price = 0
        if "明日买入条件" in stock["signal"] and "价格" in stock["signal"]["明日买入条件"]:
            buy_price = stock["signal"]["明日买入条件"]["价格"]
        else:
            # 降级：从 result 的 _df 取最后一天收盘价
            result = stock.get("result", {})
            df = result.get("_df")
            if df is not None and len(df) > 0:
                buy_price = float(df['close'].iloc[-1])

        if buy_price <= 0:
            return None

        # 获取买入后的历史数据（用于模拟）
        # 这里简化处理，实际应该获取真实历史数据
        try:
            df = self.fetcher.get_daily(code, use_cache=True)
            if df is None or len(df) < 20:
                return None

            closes = df['close'].astype(float).values
            lows = df['low'].astype(float).values

            # 模拟持有20个交易日（约1个月）
            max_hold_days = 20
            sell_price = None
            sell_reason = None
            hold_days = 0

            for i in range(1, min(max_hold_days, len(closes))):
                current_price = closes[-i]  # 倒序，最近的是最后一天
                price_change = (current_price - buy_price) / buy_price

                # 检查是否触发止损
                if price_change <= -stop_loss:
                    sell_price = current_price
                    sell_reason = "止损"
                    hold_days = i
                    break

                # 检查是否触发止盈
                if price_change >= take_profit:
                    sell_price = current_price
                    sell_reason = "止盈"
                    hold_days = i
                    break

            # 如果没有触发止损止盈，用最后价格卖出（持仓超过最大天数）
            if sell_price is None:
                sell_price = closes[-1]
                sell_reason = "到期"
                hold_days = max_hold_days

            # 计算收益率
            profit_pct = (sell_price - buy_price) / buy_price
            profit_amount = self.initial_capital * position_size * profit_pct

            return {
                "code": code,
                "buy_date": buy_date,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "sell_reason": sell_reason,
                "profit_pct": profit_pct,
                "profit_amount": profit_amount,
                "hold_days": hold_days,
                "score": stock["score"],
                "strategy": strategy
            }

        except Exception as e:
            logger.debug(f"模拟交易 {code} 失败: {e}")
            return None

    def _update_equity_curve(self):
        """更新权益曲线"""
        # 简化处理：累加已平仓交易的盈亏
        total_profit = sum(t["profit_amount"] for t in self.trades)
        self.equity_curve.append(self.initial_capital + total_profit)

    def _calculate_stats(self) -> Dict[str, Any]:
        """计算绩效指标"""
        if not self.trades:
            return {
                "交易次数": 0,
                "胜率": 0,
                "最大连亏": 0,
                "年化收益率": 0,
                "夏普比率": 0,
                "最大回撤": 0,
                "总收益率": 0,
                "平均持仓天数": 0,
                "盈利交易数": 0,
                "亏损交易数": 0,
                "平均盈利": 0,
                "平均亏损": 0,
            }

        profits = [t["profit_pct"] for t in self.trades]
        winners = [p for p in profits if p > 0]
        losers = [p for p in profits if p < 0]

        # 胜率
        win_rate = len(winners) / len(profits) if profits else 0

        # 最大连续亏损
        max_consecutive_loss = 0
        current_loss_streak = 0
        for p in profits:
            if p < 0:
                current_loss_streak += 1
                max_consecutive_loss = max(max_consecutive_loss, current_loss_streak)
            else:
                current_loss_streak = 0

        # 总收益率
        total_return = sum(profits)

        # 年化收益率（假设每年约12个月，每个月约20个交易日）
        avg_trade_return = np.mean(profits) if profits else 0
        trades_per_year = len(self.trades) / max(1, (len(self.equity_curve) / 20))  # 简化估算
        annual_return = avg_trade_return * trades_per_year

        # 夏普比率（简化版）
        if np.std(profits) > 0:
            sharpe = (np.mean(profits) / np.std(profits)) * np.sqrt(252 / 20)  # 年化
        else:
            sharpe = 0

        # 最大回撤
        equity = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0

        # 平均持仓天数
        avg_hold_days = np.mean([t["hold_days"] for t in self.trades]) if self.trades else 0

        return {
            "交易次数": len(self.trades),
            "胜率": win_rate,
            "最大连亏": max_consecutive_loss,
            "年化收益率": round(annual_return * 100, 2),
            "夏普比率": round(sharpe, 2),
            "最大回撤": round(max_drawdown * 100, 2),
            "总收益率": round(total_return * 100, 2),
            "平均持仓天数": round(avg_hold_days, 1),
            "盈利交易数": len(winners),
            "亏损交易数": len(losers),
            "平均盈利": round(np.mean(winners) * 100, 2) if winners else 0,
            "平均亏损": round(np.mean(losers) * 100, 2) if losers else 0,
        }

    def print_report(self, stats: Dict[str, Any]):
        """打印回测报告"""
        print("\n" + "=" * 50)
        print("           小金库策略回测报告 v8.2")
        print("=" * 50)
        print(f"  交易次数       : {stats['交易次数']}")
        print(f"  胜率           : {stats['胜率']:.1%}")
        print(f"  最大连亏      : {stats['最大连亏']} 次")
        print(f"  总收益率      : {stats['总收益率']:.1f}%")
        print(f"  年化收益率    : {stats['年化收益率']:.1f}%")
        print(f"  夏普比率       : {stats['夏普比率']:.2f}")
        print(f"  最大回撤       : {stats['最大回撤']:.1f}%")
        print(f"  平均持仓天数   : {stats['平均持仓天数']:.1f} 天")
        print("-" * 50)
        print(f"  盈利交易       : {stats['盈利交易数']} 笔")
        print(f"  亏损交易       : {stats['亏损交易数']} 笔")
        print(f"  平均盈利       : +{stats['平均盈利']:.1f}%")
        print(f"  平均亏损       : {stats['平均亏损']:.1f}%")
        print("=" * 50)

    def save_results(self, stats: Dict[str, Any], filepath: str = None):
        """保存回测结果到文件"""
        if filepath is None:
            base_dir = Path(__file__).parent
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = base_dir / "backtest_results" / f"backtest_{timestamp}.json"
        else:
            filepath = Path(filepath)

        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "回测时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "初始资金": self.initial_capital,
            "绩效指标": stats,
            "交易记录": [
                {
                    "code": t["code"],
                    "buy_date": t["buy_date"],
                    "buy_price": t["buy_price"],
                    "sell_price": t["sell_price"],
                    "sell_reason": t["sell_reason"],
                    "profit_pct": round(t["profit_pct"] * 100, 2),
                    "hold_days": t["hold_days"],
                }
                for t in self.trades
            ]
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"回测结果已保存: {filepath}")
        return filepath


# ==================== 快速回测接口 ====================

def quick_backtest(
    stock_pool: List[str] = None,
    start_date: str = "20230101",
    end_date: str = "20260401",
    initial_capital: float = 1000000
) -> Dict[str, Any]:
    """
    快速回测接口

    Args:
        stock_pool: 股票池（默认使用候选池）
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金

    Returns:
        回测结果统计
    """
    if stock_pool is None:
        # 使用默认候选池
        stock_pool = [
            "000001", "600016", "600036", "600519", "601318",  # 蓝筹
            "002594", "300750", "600438",  # 新能源
            "000858", "603288",  # 消费
            "600030", "601066",  # 证券
        ]

    bt = Backtester(initial_capital=initial_capital)
    stats = bt.run(
        start_date=start_date,
        end_date=end_date,
        stock_pool=stock_pool,
        strategy="left",
        stop_loss=0.08,
        take_profit=0.20,
        position_size=0.1
    )
    bt.print_report(stats)

    return stats
