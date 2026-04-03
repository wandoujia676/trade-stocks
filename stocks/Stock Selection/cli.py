"""
命令行入口
提供简单的命令行界面来执行选股、分析、监控操作
"""
import argparse
import json
import sys
from pathlib import Path

# 添加父目录到路径，以便导入stocks模块
sys.path.insert(0, str(Path(__file__).parent))

from data_fetcher import get_fetcher
from screener import get_screener
from analyzer import get_analyzer
from monitor import get_monitor, WatchlistManager, AlertManager
from selection_tracker import get_tracker
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "stock sell"))
from seller import Seller
from config import MONITOR_FILE, ALERTS_FILE


def cmd_screener(args):
    """选股命令"""
    print(f"\n{'='*50}")
    print(f"开始选股筛选...")
    print(f"{'='*50}\n")

    screener = get_screener()
    results = screener.screen(market=args.market, limit=args.limit)

    if not results:
        print("未筛选出符合条件的股票")
        return

    print(f"\n筛选结果（共{len(results)}只，按评分排序）：\n")
    print(f"{'代码':<10} {'名称/价格':<12} {'涨跌幅':<10} {'总分':<8} {'技术分':<8} {'基本面':<8} {'情绪分':<8}")
    print("-" * 100)
    print(f"{'代码':<10} {'评级':<6} {'信号':<8} {'总分':<6} {'趋势':<6} {'动量':<6} {'量价':<6} {'形态':<6} {'情绪':<6}")
    print("-" * 100)

    for i, stock in enumerate(results[:args.limit], 1):
        code = stock.get('code', '')
        rating = stock.get('评级', 'B')
        signal = stock.get('信号', '持有')
        total = stock.get('总分', 0)
        trend = stock.get('趋势分', 0)
        momentum = stock.get('动量分', 0)
        vol_price = stock.get('量价分', 0)
        pattern = stock.get('形态分', 0)
        sentiment = stock.get('情绪分', 0)

        print(f"{code:<10} {rating:<6} {signal:<8} {total:<6.1f} {trend:<6.1f} {momentum:<6.1f} {vol_price:<6.1f} {pattern:<6.1f} {sentiment:<6.1f}")

    print()

    # 保存结果到文件
    tracker = get_tracker()
    tracker.add_weekly_watchlist(results)  # 保存到 View Results/出击.txt
    tracker.save_weekly_watchlist(results)  # 保存到 View Results/weekly_watchlist.txt
    tracker.save_report()  # 保存到 View Results/出击.报告.txt

    # 过滤加仓股票单独记录
    buy_signals = ["加仓", "买入", "强烈推荐"]
    buy_stocks = [s for s in results if s.get("信号", "") in buy_signals]
    if buy_stocks:
        tracker.add_buy_signal(buy_stocks)

    print(f"结果已保存到: {tracker.tracker_file}")
    print(f"自选股已保存到: {tracker.watchlist_file}")
    print(f"报告已保存到: {tracker.tracker_file.parent / '出击.报告.txt'}")


def cmd_analyze(args):
    """分析命令"""
    symbol = args.symbol.strip()

    print(f"\n{'='*50}")
    print(f"开始分析: {symbol}")
    print(f"{'='*50}\n")

    analyzer = get_analyzer()
    report = analyzer.analyze(symbol)

    if "error" in report:
        print(f"分析失败: {report['error']}")
        return

    # 打印分析报告
    print(f"股票代码: {report['股票代码']}")
    print(f"股票名称: {report['股票名称']}")
    print(f"分析时间: {report['分析时间']}")
    print(f"最新价格: {report['最新价格']:.2f}")
    print(f"涨跌幅: {report['涨跌幅']:+.2f}%")

    # 综合信号
    signal = report.get('综合信号', {})
    print(f"\n{'='*30} 综合信号 {'='*30}")
    print(f"信号: [{signal.get('信号', '未知')}]")
    print(f"评分: {signal.get('评分', 0)}")
    print(f"评级: {signal.get('评级', 'B')}")
    print(f"建议: {signal.get('建议', '')}")
    print(f"止损位: {signal.get('止损位', '')}")
    print(f"止盈位: {signal.get('止盈位', '')}")
    if signal.get('理由'):
        print(f"理由: {', '.join(signal['理由'])}")

    # 战法评估
    warfare = report.get('战法评估', {})
    if warfare and '综合' in warfare:
        comp = warfare.get('综合', {})
        print(f"\n{'='*30} 战法评估 {'='*30}")
        print(f"综合评分: {comp.get('评分', 0)} 分 | 评级: {comp.get('评级', 'B')} | {comp.get('描述', '')}")

        # 各维度评分
        dims = ['趋势', '动量', '量价', '形态', '位置', '情绪']
        dim_details = []
        for dim in dims:
            if dim in warfare:
                score = warfare[dim].get('评分', 0)
                dim_details.append(f"{dim}:{score}")

        print(f"各维度: {' | '.join(dim_details)}")

    # 技术面
    tech = report.get('技术面', {})
    print(f"\n{'='*30} 技术分析 {'='*30}")

    ma = tech.get('均线', {})
    if '数值' in ma:
        print(f"均线: {', '.join([f'{k}={v}' for k, v in ma['数值'].items()])}")
        print(f"多头排列: {'是' if ma.get('多头排列') else '否'}")

    macd = tech.get('MACD', {})
    if 'DIF' in macd:
        print(f"MACD: DIF={macd['DIF']}, DEA={macd['DEA']}, 柱={macd['MACD柱']}")
        print(f"  位置: {macd.get('位置', '')} | {macd.get('红柱/绿柱', '')} | {macd.get('交叉信号', '')}")

    kdj = tech.get('KDJ', {})
    if 'K' in kdj:
        print(f"KDJ: K={kdj['K']}, D={kdj['D']}, J={kdj['J']}")
        print(f"  信号: {kdj.get('信号', '')} | 交叉: {kdj.get('交叉', '')}")

    boll = tech.get('BOLL', {})
    if '中轨' in boll:
        print(f"BOLL: 上轨={boll['上轨']}, 中轨={boll['中轨']}, 下轨={boll['下轨']}")
        print(f"  {boll.get('信号', '')}")

    sr = tech.get('支撑压力', {})
    if '当前价' in sr:
        print(f"支撑: {sr.get('支撑1', '')}, {sr.get('支撑2', '')}")
        print(f"压力: {sr.get('压力1', '')}, {sr.get('压力2', '')}")

    vol_price = tech.get('量价', {})
    if '信号' in vol_price:
        print(f"量价: {vol_price.get('信号', '')} | 量比: {vol_price.get('量比', 0)}")

    # K线形态
    patterns = report.get('K线形态', {})
    print(f"\n{'='*30} K线形态 {'='*30}")
    found = patterns.get('识别到的形态', [])
    if found:
        print(f"形态: {', '.join(found)}")
    else:
        print("未识别到明显形态")

    signals = patterns.get('信号', [])
    if signals:
        for s in signals:
            print(f"  [{s[0]}] {s[1]}")

    # 基本面
    fund = report.get('基本面', {})
    print(f"\n{'='*30} 基本面 {'='*30}")
    info = fund.get('获取到的信息', {})
    if info:
        for k, v in info.items():
            print(f"  {k}: {v}")
    else:
        print("  " + fund.get('状态', '暂无数据'))

    print()


def cmd_monitor(args):
    """监控命令"""
    sub_cmd = args.subcommand

    if sub_cmd == "add":
        manager = WatchlistManager()
        if manager.add(args.code, args.note or ""):
            print(f"✓ 已添加 {args.code} 到自选列表")
        else:
            print(f"✗ {args.code} 已在自选列表中")

    elif sub_cmd == "remove":
        manager = WatchlistManager()
        if manager.remove(args.code):
            print(f"✓ 已从自选列表移除 {args.code}")
        else:
            print(f"✗ {args.code} 不在自选列表中")

    elif sub_cmd == "list":
        manager = WatchlistManager()
        watchlist = manager.list()

        if not watchlist:
            print("自选列表为空")
            return

        print(f"\n自选列表（共{len(watchlist)}只）：\n")
        print(f"{'代码':<10} {'添加时间':<20} {'备注':<20}")
        print("-" * 60)
        for w in watchlist:
            print(f"{w['code']:<10} {w.get('added_at', ''):<20} {w.get('note', ''):<20}")
        print()

    elif sub_cmd == "check":
        print(f"\n{'='*50}")
        print(f"检查自选股信号...")
        print(f"{'='*50}\n")

        monitor = get_monitor()
        signals = monitor.check_all()

        if not signals:
            print("未发现异常信号")
            return

        print(f"发现 {len(signals)} 个信号：\n")
        for sig in signals:
            level_icon = {"success": "✓", "warning": "⚠", "danger": "✗", "info": "ℹ"}.get(sig.get('level', ''), '•')
            print(f"{level_icon} [{sig['type']}] {sig['code']}: {sig['message']}")
            print(f"   建议: {sig['suggestion']}\n")

    elif sub_cmd == "alerts":
        manager = AlertManager()
        alerts = manager.get_unread()

        if not alerts:
            print("暂无未读提醒")
            return

        print(f"\n未读提醒（共{len(alerts)}条）：\n")
        for a in alerts:
            level_icon = {"success": "✓", "warning": "⚠", "danger": "✗", "info": "ℹ"}.get(a.get('level', ''), '•')
            print(f"{level_icon} [{a['type']}] {a['code']}: {a['message']}")
            print(f"   时间: {a.get('time', '')} | 建议: {a.get('suggestion', '')}\n")

        # 标记为已读
        manager.mark_all_read()
        print("已标记所有提醒为已读")


def cmd_sell(args):
    """卖出决策分析命令"""
    if args.positions:
        # 分析指定的持仓
        positions = args.positions
    elif args.test:
        # 测试模式
        positions = None
    else:
        print("请提供持仓信息，格式: sell 600519@1700 000001@12.5")
        return

    seller = Seller()

    print(f"\n{'='*60}")
    print(f"卖出决策分析")
    print(f"{'='*60}\n")

    if positions is None:
        # 测试模式
        print("【测试模式】演示卖出分析\n")
        import random

        test_cases = [
            {"code": "600519", "entry_price": 1700.0, "holding_days": 5, "current_price": 1700.0 * random.uniform(0.95, 1.15)},
            {"code": "000001", "entry_price": 12.5, "holding_days": 8, "current_price": 12.5 * random.uniform(0.95, 1.15)},
            {"code": "300750", "entry_price": 180.0, "holding_days": 3, "current_price": 180.0 * random.uniform(0.95, 1.15)},
        ]

        results = []
        for tc in test_cases:
            r = seller.analyze_position(tc['code'], tc['entry_price'], holding_days=tc['holding_days'])
            if not r.get('error'):
                r['current_price'] = tc['current_price']
                # 重新计算盈亏
                from sell_strategy import get_sell_strategy
                strategy = get_sell_strategy()
                pl = strategy.calculate_profit_loss(tc['entry_price'], tc['current_price'])
                r['盈亏分析'] = pl
                # 重新生成分档
                sell_plan = strategy.generate_sell_plan(
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
        # 真实分析
        positions = seller.parse_positions(positions)
        if not positions:
            print("未识别到有效持仓股票，请使用格式: 600519@1700")
            return

        print(f"正在分析 {len(positions)} 只持仓股票...\n")

        results = seller.analyze_multiple(positions)

        for r in results:
            print(seller.format_report(r))

        if len(results) > 1:
            print(seller.format_summary(results))


def cmd_realtime(args):
    """实时行情命令"""
    fetcher = get_fetcher()
    code = args.symbol.strip()

    print(f"\n获取 {code} 实时行情...\n")

    data = fetcher.get_realtime(code)

    if not data:
        print("获取失败")
        return

    print(f"代码: {data.get('code', '')}")
    print(f"名称: {data.get('name', '未知')}")
    print(f"最新价: {data.get('price', 0):.2f}")
    print(f"涨跌幅: {data.get('change_pct', 0):+.2f}%")
    print(f"今开: {data.get('open', 0):.2f}")
    print(f"昨收: {data.get('prev_close', 0):.2f}")
    print(f"最高: {data.get('high', 0):.2f}")
    print(f"最低: {data.get('low', 0):.2f}")
    print(f"成交量: {data.get('volume', 0):,.0f}")
    print(f"成交额: {data.get('amount', 0):,.2f}")
    print(f"换手率: {data.get('turnover', 0):.2f}%")
    print(f"数据源: {data.get('source', 'unknown')}")
    print()


def main():
    parser = argparse.ArgumentParser(description="股票分析系统")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 选股命令
    parser_screener = subparsers.add_parser("screener", help="筛选股票")
    parser_screener.add_argument("--market", "-m", default="全市场", help="市场范围")
    parser_screener.add_argument("--limit", "-l", type=int, default=20, help="返回数量")
    parser_screener.add_argument("--output", "-o", help="结果保存路径")

    # 分析命令
    parser_analyze = subparsers.add_parser("analyze", help="分析股票")
    parser_analyze.add_argument("symbol", help="股票代码")

    # 监控命令
    parser_monitor = subparsers.add_parser("monitor", help="监控自选股")
    subparsers_monitor = parser_monitor.add_subparsers(dest="subcommand", help="监控子命令")
    parser_monitor_add = subparsers_monitor.add_parser("add", help="添加自选")
    parser_monitor_add.add_argument("code", help="股票代码")
    parser_monitor_add.add_argument("--note", "-n", default="", help="备注")

    parser_monitor_remove = subparsers_monitor.add_parser("remove", help="移除自选")
    parser_monitor_remove.add_argument("code", help="股票代码")

    parser_monitor_list = subparsers_monitor.add_parser("list", help="列出自选")

    parser_monitor_check = subparsers_monitor.add_parser("check", help="检查信号")

    parser_monitor_alerts = subparsers_monitor.add_parser("alerts", help="查看提醒")

    # 实时行情命令
    parser_realtime = subparsers.add_parser("realtime", help="实时行情")
    parser_realtime.add_argument("symbol", help="股票代码")

    # 卖出决策命令
    parser_sell = subparsers.add_parser("sell", help="卖出决策分析")
    parser_sell.add_argument('positions', nargs='*', help='持仓股票，格式: 600519@1700')
    parser_sell.add_argument('--test', action='store_true', help='运行测试模式')

    args = parser.parse_args()

    if args.command == "screener":
        cmd_screener(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "monitor":
        cmd_monitor(args)
    elif args.command == "realtime":
        cmd_realtime(args)
    elif args.command == "sell":
        cmd_sell(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
