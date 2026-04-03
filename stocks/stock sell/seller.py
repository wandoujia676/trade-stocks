"""
卖出决策引擎 - 分析持仓股票的最佳卖出时机和方案
基于九本书理论知识（《一买即涨》《交易真相》《股道人生》《量学》等）

使用方法：
    python seller.py 600519@1700 000001@12.5
    python seller.py --test  # 运行测试模式
"""

import sys
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# 添加父目录(Stock Selection)到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "Stock Selection"))

from data_fetcher import get_fetcher
from warfare import get_warfare
from sell_signals import get_sell_signals
from sell_strategy import get_sell_strategy

logger = logging.getLogger(__name__)


class Seller:
    """
    卖出决策引擎

    分析持仓股票，输出：
    1. 综合卖出评分（0-100）
    2. 卖出信号列表（来自九本书）
    3. 分档卖出方案
    4. 持仓周期建议
    5. 风险提示
    """

    def __init__(self):
        self.data_fetcher = get_fetcher()
        self.warfare = get_warfare()
        self.sell_signals = get_sell_signals()
        self.sell_strategy = get_sell_strategy()

        # 股票代码到名称的映射
        self.stock_names = {
            "000001": "平安银行", "600016": "民生银行", "600036": "招商银行",
            "601166": "兴业银行", "601288": "农业银行", "601328": "交通银行",
            "601398": "工商银行", "601818": "光大银行", "600000": "浦发银行",
            "600030": "中信证券", "600837": "海通证券", "601066": "中信建投",
            "601211": "国泰君安", "601688": "华泰证券", "000776": "广发证券",
            "601318": "中国平安", "601601": "新华保险", "601628": "中国人寿",
            "000568": "泸州老窖", "000858": "五粮液", "600519": "贵州茅台",
            "603288": "海天味业", "000799": "酒鬼酒", "002304": "洋河股份",
            "600809": "山西汾酒", "000596": "古井贡酒",
            "300750": "宁德时代", "002594": "比亚迪", "600438": "通威股份",
            "601012": "隆基绿能", "002466": "天齐锂业", "600089": "特变电工",
            "600900": "长江电力", "000002": "万科A", "000063": "中兴通讯",
            "000100": "TCL科技", "002230": "科大讯飞", "002241": "歌尔股份",
            "002415": "海康威视", "002460": "赣锋锂业", "300033": "同花顺",
            "300059": "东方财富", "300124": "汇川技术", "000977": "浪潮信息",
            "600570": "恒生电子", "600588": "用友网络", "002410": "广联达",
            "000538": "云南白药", "600276": "恒瑞医药", "603259": "药明康德",
            "300015": "爱尔眼科", "002007": "华兰生物", "000661": "长春高新",
            "300760": "迈瑞医疗", "600196": "复星医药", "300003": "乐普医疗",
            "002371": "北方华创", "688981": "中芯国际", "603501": "韦尔股份",
            "002236": "大华股份", "603986": "兆易创新", "002049": "紫光国微",
            "688008": "澜起科技", "000725": "京东方A", "300866": "安克创新",
            "002475": "立讯精密", "300207": "欣旺达", "002351": "漫步者",
            "300024": "机器人", "300058": "蓝色光标", "002027": "分众传媒",
            "300113": "顺网科技", "600048": "保利发展", "600606": "绿地控股",
            "001979": "招商蛇口", "600383": "金地集团", "000671": "阳光城",
            "600309": "万华化学", "600352": "浙江龙盛", "000830": "鲁西化工",
            "002601": "龙佰集团", "600989": "华鲁恒升", "601216": "君正集团",
            "601100": "恒立液压", "600031": "三一重工", "000425": "徐工机械",
            "002048": "宁波华翔", "600893": "航发动力", "000768": "中航西飞",
            "002013": "中航机电", "600316": "洪都航空", "601698": "中国卫通",
            "600760": "中航沈飞", "002557": "恰恰食品",
        }

    def parse_positions(self, position_strs: List[str]) -> List[Dict[str, Any]]:
        """
        解析持仓字符串

        Args:
            position_strs: ["600519@1700", "000001@12.5", "2026-03-15"]

        Returns:
            [{"code": "600519", "entry_price": 1700.0, "entry_date": "2026-03-15"}, ...]
        """
        positions = []

        for pos_str in position_strs:
            pos_str = pos_str.strip()
            if not pos_str:
                continue

            # 支持格式：
            # - 600519@1700
            # - 600519@1700@2026-03-15
            # - 600519@1700元
            parts = pos_str.replace('元', '').split('@')

            code = parts[0].strip()
            if not code:
                continue

            # 补全代码（6位）
            code = code.zfill(6)

            entry_price = float(parts[1].strip()) if len(parts) > 1 else 0.0

            entry_date = parts[2].strip() if len(parts) > 2 else datetime.now().strftime("%Y-%m-%d")

            positions.append({
                "code": code,
                "entry_price": entry_price,
                "entry_date": entry_date
            })

        return positions

    def analyze_position(self, code: str, entry_price: float,
                        entry_date: str = None, holding_days: int = None) -> Dict[str, Any]:
        """
        分析单只持仓股票的卖出时机

        Args:
            code: 股票代码
            entry_price: 买入价
            entry_date: 买入日期（YYYY-MM-DD），用于计算持仓天数
            holding_days: 持仓天数（如果指定则覆盖计算）

        Returns:
            完整的卖出分析报告
        """
        result = {
            "code": code,
            "name": self.stock_names.get(code, "未知"),
            "entry_price": entry_price,
            "error": None
        }

        # 1. 获取股票数据
        try:
            df = self.data_fetcher.get_daily(code)
            if df is None or len(df) < 20:
                result["error"] = f"数据获取失败"
                return result
        except Exception as e:
            result["error"] = f"数据获取异常: {str(e)}"
            return result

        # 2. 计算持仓天数
        if holding_days is None:
            if entry_date:
                try:
                    entry = datetime.strptime(entry_date, "%Y-%m-%d")
                    holding_days = (datetime.now() - entry).days
                except:
                    holding_days = 5  # 默认5天
            else:
                holding_days = 5  # 默认5天

        # 3. 获取当前价格
        current_price = float(df['close'].iloc[-1])
        result["current_price"] = round(current_price, 2)

        # 4. 执行战法评分（用于止盈止损基准）
        try:
            warfare_result = self.warfare.evaluate(df)
            composite_score = warfare_result.get("综合", {}).get("评分", 55)
            result["warfare_score"] = composite_score
            result["warfare_rating"] = warfare_result.get("综合", {}).get("评级", "B+")
        except:
            composite_score = 55  # 默认

        # 5. 检测卖出信号
        try:
            signals_result = self.sell_signals.detect_all_signals(df)
            signal_score = signals_result.get("total_score", 0)
            signals_list = signals_result.get("signals", [])
            result["signals"] = signals_list
            result["signal_count"] = signals_result.get("signal_count", 0)
            result["signal_score"] = signal_score
            result["signal_details"] = signals_result.get("details", {})
        except Exception as e:
            logger.error(f"卖出信号检测异常: {e}")
            signal_score = 0
            signals_list = []

        # 6. 生成分档卖出方案
        try:
            sell_plan = self.sell_strategy.generate_sell_plan(
                entry_price=entry_price,
                current_price=current_price,
                composite_score=composite_score,
                holding_days=holding_days,
                signal_score=signal_score
            )
            result.update(sell_plan)
        except Exception as e:
            logger.error(f"卖出策略计算异常: {e}")
            result["error"] = f"策略计算异常: {str(e)}"

        # 7. 添加买入理由（如果有）
        result["holding_days"] = holding_days

        return result

    def analyze_multiple(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        分析多只持仓股票

        Args:
            positions: [{"code": "600519", "entry_price": 1700, "entry_date": "2026-03-15"}, ...]

        Returns:
            每只股票的分析结果列表
        """
        results = []
        for pos in positions:
            result = self.analyze_position(
                code=pos["code"],
                entry_price=pos["entry_price"],
                entry_date=pos.get("entry_date"),
                holding_days=pos.get("holding_days")
            )
            results.append(result)
        return results

    def format_report(self, result: Dict[str, Any]) -> str:
        """
        格式化输出卖出分析报告

        Returns:
            可读的卖出建议报告
        """
        if result.get("error"):
            return f"【{result['code']} {result.get('name', '')}】\n  错误: {result['error']}"

        code = result['code']
        name = result.get('name', '未知')
        entry = result['entry_price']
        current = result['current_price']
        score = result.get('综合卖出评分', 0)
        suggestion = result.get('建议', '继续持有')
        holding_days = result.get('holding_days', 0)

        # 盈亏
        pl = result.get('盈亏分析', {})
        pl_amount = pl.get('盈亏金额', 0)
        pl_pct = pl.get('盈亏比例', 0)
        pl_status = pl.get('持仓状态', '')

        lines = []
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"【卖出分析报告】{code} {name}")
        lines.append("=" * 60)
        lines.append(f"买入价: {entry:.2f} | 当前价: {current:.2f} | 持仓天数: {holding_days}天")
        lines.append(f"盈亏: {'+' if pl_amount >= 0 else ''}{pl_amount:.2f}元 ({'+' if pl_pct >= 0 else ''}{pl_pct:.2f}%) - {pl_status}")
        lines.append("-" * 60)

        # 综合评分和建议
        rating_text = ""
        if score >= 80:
            rating_text = "[强烈卖出]"
        elif score >= 65:
            rating_text = "[考虑减仓]"
        elif score >= 50:
            rating_text = "[谨慎持有]"
        else:
            rating_text = "[继续持有]"

        lines.append(f"综合卖出评分: {rating_text} {score:.1f}分")
        lines.append(f"卖出建议: {suggestion}")
        lines.append("")

        # 卖出信号
        signals = result.get('signals', [])
        if signals:
            lines.append("【卖出信号】（来自九本书理论）")
            for s in signals:
                lines.append(f"  - {s['type']} | 权重{s['weight']}分 | {s['source']}")
                if s.get('desc'):
                    lines.append(f"    → {s['desc']}")
            lines.append("")

        # 止损止盈位
        stop_loss = result.get('止损位', {})
        take_profit = result.get('止盈位', {})
        if stop_loss:
            lines.append(f"止损位: {stop_loss.get('止损价', '-')} 元 (亏损{stop_loss.get('止损比例', '-')}%)")
        if take_profit:
            lines.append(f"止盈区间: {take_profit.get('第一止盈价', '-')} ~ {take_profit.get('第二止盈价', '-')} 元 ({take_profit.get('止盈区间', '')})")
        lines.append("")

        # 分档卖出方案
        tiers = result.get('分档方案', [])
        if tiers:
            lines.append("【分档卖出方案】")
            for t in tiers:
                lines.append(f"  {t['档位']} {t['仓位']}仓位: {t['条件']}")
                lines.append(f"    理由: {t['理由']}")
                if '预计盈利' in t:
                    lines.append(f"    预计: {t['预计盈利']}")
                if '风险' in t:
                    lines.append(f"    风险: {t['风险']}")
            lines.append("")

        # 持仓周期建议
        period = result.get('持仓周期建议', {})
        if period:
            lines.append(f"【持仓周期建议】")
            lines.append(f"  策略类型: {period.get('策略类型', '-')}")
            lines.append(f"  建议: {period.get('建议', '-')}")
            lines.append("")

        # 风险提示
        risk = result.get('风险提示', '')
        if risk:
            lines.append(f"【风险提示】 {risk}")
            lines.append("")

        lines.append("=" * 60)
        lines.append("")

        return "\n".join(lines)

    def format_summary(self, results: List[Dict[str, Any]]) -> str:
        """
        格式化多只股票的汇总报告
        """
        lines = []
        lines.append("")
        lines.append("=" * 60)
        lines.append("【持仓卖出分析汇总】")
        lines.append("=" * 60)

        for r in results:
            if r.get("error"):
                lines.append(f"- {r['code']} {r.get('name', '')}: {r['error']}")
                continue

            score = r.get('综合卖出评分', 0)
            suggestion = r.get('建议', '持有')
            pl_pct = r.get('盈亏分析', {}).get('盈亏比例', 0)

            if score >= 80:
                icon = "[强烈卖出]"
            elif score >= 65:
                icon = "[考虑减仓]"
            elif score >= 50:
                icon = "[谨慎持有]"
            else:
                icon = "[继续持有]"

            lines.append(f"{icon} {r['code']} {r.get('name', '')}: {score:.0f}分 - {suggestion} ({'+' if pl_pct >= 0 else ''}{pl_pct:.2f}%)")

        lines.append("")
        lines.append("提示: [继续持有] | [谨慎持有] | [考虑减仓] | [强烈卖出]")
        lines.append("=" * 60)
        lines.append("")

        return "\n".join(lines)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='卖出决策分析')
    parser.add_argument('positions', nargs='*', help='持仓股票，如: 600519@1700 000001@12.5')
    parser.add_argument('--test', action='store_true', help='运行测试模式')
    parser.add_argument('--days', type=int, default=5, help='持仓天数（测试用）')

    args = parser.parse_args()

    seller = Seller()

    if args.test or not args.positions:
        # 测试模式：使用模拟数据
        print("=" * 60)
        print("【测试模式】使用模拟数据演示卖出分析")
        print("=" * 60)

        test_cases = [
            {"code": "600519", "entry_price": 1700.0, "holding_days": 5},
            {"code": "000001", "entry_price": 12.5, "holding_days": 8},
            {"code": "300750", "entry_price": 180.0, "holding_days": 3},
        ]

        for tc in test_cases:
            # 模拟当前价格（买入价基础上浮动）
            import random
            tc['current_price'] = tc['entry_price'] * random.uniform(0.95, 1.15)

        results = []
        for tc in test_cases:
            # 跳过真实数据获取，直接构建结果用于演示
            r = seller.analyze_position(tc['code'], tc['entry_price'], holding_days=tc['holding_days'])
            if not r.get('error'):
                r['current_price'] = tc['current_price']
                # 重新计算盈亏
                pl = seller.sell_strategy.calculate_profit_loss(tc['entry_price'], tc['current_price'])
                r['盈亏分析'] = pl
                # 重新生成分档
                sell_plan = seller.sell_strategy.generate_sell_plan(
                    entry_price=tc['entry_price'],
                    current_price=tc['current_price'],
                    composite_score=r.get('warfare_score', 55),
                    holding_days=tc['holding_days'],
                    signal_score=r.get('signal_score', 0)
                )
                r.update(sell_plan)
            results.append(r)
            print(seller.format_report(r))

        print(seller.format_summary(results))

    else:
        # 真实分析模式
        positions = seller.parse_positions(args.positions)
        if not positions:
            print("未识别到有效持仓股票，请使用格式: 600519@1700")
            return

        print(f"正在分析 {len(positions)} 只持仓股票...")
        print("")

        results = seller.analyze_multiple(positions)

        for r in results:
            print(seller.format_report(r))

        if len(results) > 1:
            print(seller.format_summary(results))


if __name__ == "__main__":
    main()
