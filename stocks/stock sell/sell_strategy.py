"""
分档卖出策略模块 - 基于九本书的止盈止损规则
整合《一买即涨》《交易真相》《股道人生》等卖出理论

核心策略：
1. 根据持仓收益率确定分档卖出方案
2. 结合卖出信号强度调整策略
3. 遵循《股道人生》仓位原则：分批卖出
4. 参考《交易真相》：截断亏损，让利润奔跑
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class SellStrategy:
    """
    分档卖出策略计算器

    止盈止损基准（来自 SELECTION_LOGIC.txt）：
    - 综合评分>=55：止损-5%，止盈15-20%
    - 综合评分<55：止损-3%，止盈10%

    分档卖出策略规则：
    - 持仓盈利 > 20%：50%锁利 + 30%减亏 + 20%博趋势
    - 持仓盈利 10-20%：60%止盈 + 40%观望
    - 持仓盈利 5-10%：建议持有
    - 持仓亏损：触及止损坚决出
    """

    # 止盈止损配置
    STOP_LOSS_HIGH = 0.05   # 高评分止损5%
    STOP_LOSS_LOW = 0.03     # 低评分止损3%
    TAKE_PROFIT_HIGH = (0.15, 0.20)  # 高评分止盈15-20%
    TAKE_PROFIT_LOW = 0.10   # 低评分止盈10%

    # 止损7-8%原则（《股道人生》）
    STOP_LOSS_GU_DAO = 0.075

    def __init__(self):
        pass

    def calculate_profit_loss(self, entry_price: float, current_price: float) -> Dict[str, Any]:
        """
        计算持仓盈亏情况

        Returns:
            {
                "持仓天数": 5,
                "盈亏金额": 1000,
                "盈亏比例": 0.05,
                "持仓状态": "盈利中"
            }
        """
        if entry_price <= 0 or current_price <= 0:
            return {"error": "价格数据无效"}

        profit = current_price - entry_price
        profit_pct = profit / entry_price

        return {
            "买入价": entry_price,
            "当前价": current_price,
            "盈亏金额": round(profit, 2),
            "盈亏比例": round(profit_pct * 100, 2),  # 百分比
            "持仓状态": self._get_profit_status(profit_pct)
        }

    def _get_profit_status(self, profit_pct: float) -> str:
        """根据盈亏比例判断持仓状态"""
        if profit_pct >= 0.20:
            return "大幅盈利"
        elif profit_pct >= 0.10:
            return "盈利中"
        elif profit_pct >= 0.05:
            return "小幅盈利"
        elif profit_pct >= 0:
            return "微盈"
        elif profit_pct >= -0.03:
            return "小幅亏损"
        elif profit_pct >= -0.08:
            return "亏损中"
        else:
            return "大幅亏损"

    def calculate_stop_loss(self, entry_price: float, composite_score: float = 55) -> Dict[str, float]:
        """
        计算止损位

        Args:
            entry_price: 买入价
            composite_score: 综合评分（用于判断用哪个规则）

        Returns:
            {"止损价": 95.0, "止损比例": -0.05}
        """
        if composite_score >= 55:
            stop_loss_pct = self.STOP_LOSS_HIGH
        else:
            stop_loss_pct = self.STOP_LOSS_LOW

        # 《股道人生》止损7-8%原则
        if stop_loss_pct < self.STOP_LOSS_GU_DAO:
            stop_loss_pct = self.STOP_LOSS_GU_DAO

        stop_loss_price = entry_price * (1 - stop_loss_pct)

        return {
            "止损价": round(stop_loss_price, 2),
            "止损比例": round(-stop_loss_pct * 100, 1)  # 转为正数表示亏损
        }

    def calculate_take_profit(self, entry_price: float, composite_score: float = 55) -> Dict[str, Any]:
        """
        计算止盈位

        Returns:
            {"第一止盈价": 115.0, "第二止盈价": 120.0, "止盈区间": "15-20%"}
        """
        if composite_score >= 55:
            tp_min, tp_max = self.TAKE_PROFIT_HIGH
        else:
            tp_min = self.TAKE_PROFIT_LOW
            tp_max = self.TAKE_PROFIT_LOW

        profit_min_price = entry_price * (1 + tp_min)
        profit_max_price = entry_price * (1 + tp_max)

        return {
            "第一止盈价": round(profit_min_price, 2),
            "第二止盈价": round(profit_max_price, 2),
            "止盈区间": f"{int(tp_min*100)}-{int(tp_max*100)}%"
        }

    def generate_sell_plan(self, entry_price: float, current_price: float,
                          composite_score: float = 55, holding_days: int = 5,
                          signal_score: float = 0) -> Dict[str, Any]:
        """
        生成分档卖出方案

        Args:
            entry_price: 买入价
            current_price: 当前价
            composite_score: 综合评分
            holding_days: 持仓天数
            signal_score: 卖出信号强度（0-100）

        Returns:
            {
                "综合卖出评分": 75,
                "建议": "考虑减仓",
                "盈亏分析": {...},
                "分档方案": [...],
                "持仓建议": "...",
                "风险提示": "..."
            }
        """
        # 1. 计算盈亏
        pl = self.calculate_profit_loss(entry_price, current_price)
        if "error" in pl:
            return pl

        profit_pct = pl["盈亏比例"] / 100  # 转为小数

        # 2. 计算止损止盈位
        stop_loss = self.calculate_stop_loss(entry_price, composite_score)
        take_profit = self.calculate_take_profit(entry_price, composite_score)

        # 3. 计算综合卖出评分
        sell_score = self._calculate_sell_score(profit_pct, signal_score, holding_days)

        # 4. 生成建议
        suggestion = self._get_suggestion(sell_score, profit_pct)

        # 5. 生成分档方案
        tiers = self._generate_tiers(entry_price, current_price, profit_pct,
                                     stop_loss, take_profit, sell_score)

        # 6. 持仓周期建议
        period_suggestion = self._get_period_suggestion(holding_days, profit_pct, sell_score)

        # 7. 风险提示
        risk_warning = self._get_risk_warning(signal_score, profit_pct, current_price,
                                            stop_loss["止损价"])

        return {
            "股票代码": "",
            "综合卖出评分": round(sell_score, 1),
            "建议": suggestion,
            "盈亏分析": pl,
            "止损位": stop_loss,
            "止盈位": take_profit,
            "分档方案": tiers,
            "持仓周期建议": period_suggestion,
            "风险提示": risk_warning,
            "卖出信号来源": "九本书理论" if signal_score > 0 else "暂无明显信号"
        }

    def _calculate_sell_score(self, profit_pct: float, signal_score: float, holding_days: int) -> float:
        """
        计算综合卖出评分

        卖出评分 = 技术见顶信号分×0.30 + 持仓收益分×0.25 + 趋势转折分×0.20 + 量价背离分×0.15 + 持仓周期分×0.10
        """
        # 技术见顶信号（30%）
        tech_score = signal_score * 0.30

        # 持仓收益分（25%）：盈利越多越考虑卖
        # 盈利>20%得25分，盈利<-8%得25分（止损）
        if profit_pct > 0.20:
            profit_score = 25
        elif profit_pct > 0.10:
            profit_score = 18
        elif profit_pct > 0.05:
            profit_score = 12
        elif profit_pct > 0:
            profit_score = 8
        elif profit_pct > -0.05:
            profit_score = 5  # 小亏，观望
        else:
            profit_score = min(25, abs(profit_pct) * 250)  # 亏损越大越要止损
        profit_score = profit_score * 0.25

        # 趋势转折分（20%）：根据持仓天数和盈亏综合判断
        if holding_days <= 3:
            # 短线：快速盈利则考虑卖
            if profit_pct > 0.05:
                trend_score = 15
            elif profit_pct < -0.03:
                trend_score = 20  # 短线亏损必须出
            else:
                trend_score = 10
        elif holding_days <= 10:
            # 偏短线
            if profit_pct > 0.15:
                trend_score = 15
            elif profit_pct > 0.05:
                trend_score = 10
            else:
                trend_score = 8
        else:
            # 中线：给更多时间
            if profit_pct > 0.20:
                trend_score = 12
            elif profit_pct > 0.10:
                trend_score = 8
            else:
                trend_score = 5
        trend_score = trend_score * 0.20

        # 量价背离分（15%）- 这里简化处理，由signal_score覆盖
        vol_price_score = 0
        if signal_score > 30:
            vol_price_score = 10 * 0.15
        elif signal_score > 15:
            vol_price_score = 5 * 0.15

        # 持仓周期分（10%）
        if holding_days <= 3:
            period_score = 8
        elif holding_days <= 10:
            period_score = 6
        elif holding_days <= 30:
            period_score = 4
        else:
            period_score = 2
        period_score = period_score * 0.10

        total = tech_score + profit_score + trend_score + vol_price_score + period_score
        return min(100, max(0, total))

    def _get_suggestion(self, sell_score: float, profit_pct: float) -> str:
        """根据卖出评分和盈亏获取建议"""
        if sell_score >= 80:
            return "强烈卖出"
        elif sell_score >= 65:
            return "考虑减仓"
        elif sell_score >= 50:
            if profit_pct > 0.10:
                return "分批减仓锁利"
            elif profit_pct < -0.05:
                return "止损或观望"
            else:
                return "谨慎持有"
        else:
            if profit_pct > 0.15:
                return "可适当减仓"
            elif profit_pct < -0.08:
                return "建议止损"
            else:
                return "继续持有"

    def _generate_tiers(self, entry_price: float, current_price: float,
                       profit_pct: float, stop_loss: Dict, take_profit: Dict,
                       sell_score: float) -> List[Dict[str, Any]]:
        """
        生成分档卖出方案

        规则：
        - 盈利>20%：50%锁利 + 30%减亏 + 20%博趋势
        - 盈利10-20%：60%止盈 + 40%观望
        - 盈利5-10%：30%减仓 + 70%持有
        - 盈利<5%或亏损：止损建议
        """
        tiers = []

        if profit_pct > 0.20:
            # 大幅盈利：分批锁利
            tiers.append({
                "档位": "第一档",
                "仓位": "50%",
                "条件": f"反弹至 {take_profit['第一止盈价']} 元附近",
                "理由": "先锁利，保留子弹",
                "预计盈利": f"+{(take_profit['第一止盈价']/entry_price - 1)*100:.0f}%"
            })
            tiers.append({
                "档位": "第二档",
                "仓位": "30%",
                "条件": f"再涨 {((take_profit['第二止盈价']/current_price - 1))*100:.0f}% 至 {take_profit['第二止盈价']} 元",
                "理由": "继续扩大利润",
                "预计盈利": "累计+15-20%"
            })
            tiers.append({
                "档位": "第三档",
                "仓位": "20%",
                "条件": f"止损设为 {stop_loss['止损价']} 元",
                "理由": "留底仓博取更大趋势，跌破坚决出",
                "风险": f"最大亏损 {stop_loss['止损比例']}%"
            })

        elif profit_pct > 0.10:
            # 盈利中：60%止盈
            tiers.append({
                "档位": "第一档",
                "仓位": "60%",
                "条件": f"触及止盈 {take_profit['第一止盈价']} 元",
                "理由": "已达到目标位，锁利为先（《交易真相》）",
                "预计盈利": f"+{(take_profit['第一止盈价']/entry_price - 1)*100:.0f}%"
            })
            tiers.append({
                "档位": "第二档",
                "仓位": "40%",
                "条件": f"止损上移至 {current_price * 0.98:.2f} 元",
                "理由": "留40%仓位博趋势，不破不出",
                "风险": "可能回撤"
            })

        elif profit_pct > 0.05:
            # 小幅盈利：30%减仓
            sell_price = entry_price * (1 + profit_pct * 0.5)  # 卖出一半利润
            tiers.append({
                "档位": "第一档",
                "仓位": "30%",
                "条件": f"回调至 {sell_price:.2f} 元",
                "理由": "先落袋部分利润",
                "预计盈利": f"+{profit_pct*50:.0f}%"
            })
            tiers.append({
                "档位": "第二档",
                "仓位": "70%",
                "条件": f"止损设为 {stop_loss['止损价']} 元",
                "理由": "等待更高目标",
                "风险": "可能回撤到成本"
            })

        elif profit_pct > 0:
            # 微盈：观望
            tiers.append({
                "档位": "建议",
                "仓位": "-",
                "条件": "继续持有，等待更高目标位",
                "理由": "盈利有限，不急于卖出",
                "风险": "可能转盈为亏"
            })

        else:
            # 亏损
            if profit_pct >= -0.05:
                # 小亏：给机会
                tiers.append({
                    "档位": "建议",
                    "仓位": "-",
                    "条件": f"止损位 {stop_loss['止损价']} 元",
                    "理由": "《交易真相》截断亏损，小亏不走可能变大亏",
                    "风险": f"可能亏损 {abs(profit_pct)*100:.1f}%"
                })
            else:
                # 大亏：必须出
                tiers.append({
                    "档位": "紧急",
                    "仓位": "100%",
                    "条件": f"立即止损 {stop_loss['止损价']} 元",
                    "理由": "《股道人生》止损7-8%，已达或超过！",
                    "风险": f"已亏损 {abs(profit_pct)*100:.1f}%，不可再持"
                })

        return tiers

    def _get_period_suggestion(self, holding_days: int, profit_pct: float, sell_score: float) -> Dict[str, str]:
        """
        获取持仓周期建议

        规则：
        - 1-3天：短线策略，严格止损
        - 4-10天：偏短线，看量能
        - 11-30天：中线策略
        - >30天：长线思路
        """
        if holding_days <= 3:
            if profit_pct > 0.05:
                suggestion = "短线已有盈利，建议分批减仓锁利"
                strategy = "短线"
            elif profit_pct < -0.03:
                suggestion = "短线亏损超出预期，建议止损（《交易真相》）"
                strategy = "短线-止损"
            else:
                suggestion = "短线微盈或持平，继续观察"
                strategy = "短线-观望"
        elif holding_days <= 10:
            if sell_score >= 65:
                suggestion = "出现卖出信号，建议减仓"
                strategy = "偏短线-减仓"
            elif profit_pct > 0.10:
                suggestion = "盈利可观，可考虑分批卖出"
                strategy = "偏短线-锁利"
            else:
                suggestion = "继续持有，观察趋势是否延续"
                strategy = "偏短线-持有"
        elif holding_days <= 30:
            if sell_score >= 65:
                suggestion = "中线出现卖点，建议减仓"
                strategy = "中线-减仓"
            elif profit_pct > 0.15:
                suggestion = "中线盈利良好，可适当减仓"
                strategy = "中线-部分了结"
            else:
                suggestion = "趋势未破可继续持有，跌破均线则出"
                strategy = "中线-持有"
        else:
            if sell_score >= 65:
                suggestion = "长期持有出现卖点，建议减仓"
                strategy = "长线-减仓"
            elif profit_pct > 0.20:
                suggestion = "长线盈利丰厚，可考虑分批了结"
                strategy = "长线-了结"
            else:
                suggestion = "基本面向好可持有，趋势破位则出"
                strategy = "长线-持有"

        return {
            "持仓天数": holding_days,
            "策略类型": strategy,
            "建议": suggestion
        }

    def _get_risk_warning(self, signal_score: float, profit_pct: float,
                         current_price: float, stop_loss_price: float) -> str:
        """生成风险提示"""
        warnings = []

        if signal_score >= 50:
            warnings.append("[警告] 多个见顶信号，建议密切关注")

        if signal_score >= 30:
            warnings.append("[警告] 出现明显卖出信号，注意锁定利润")

        if profit_pct > 0.20:
            warnings.append("盈利已超20%，注意分批止盈")

        if profit_pct < -0.05:
            warnings.append("[警告] 已亏损超过5%，注意止损纪律")

        if current_price < stop_loss_price * 1.02:
            warnings.append("[紧急] 接近止损位，密切关注！")

        if not warnings:
            warnings.append("暂无明显风险提示")

        return " ".join(warnings)


# 单例
_sell_strategy_instance = None

def get_sell_strategy() -> SellStrategy:
    """获取卖出策略单例"""
    global _sell_strategy_instance
    if _sell_strategy_instance is None:
        _sell_strategy_instance = SellStrategy()
    return _sell_strategy_instance
