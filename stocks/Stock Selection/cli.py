"""
命令行入口
提供简单的命令行界面来执行选股、分析、监控操作
"""
import argparse
import json
import sys
from pathlib import Path

# 小金库版本
VERSION = "8.1"

# 版本更新记录
VERSION_LOG = [
    ("8.1", "2026-04-24", [
        "修复: 量在价先判断区分放量上涨 vs 放量下跌（后者扣分）",
        "修复: 底部堆量判断增加价格止跌条件（放量下跌不加分）",
        "修复: 放量反弹区分上涨 vs 下跌（下跌扣分）",
    ]),
    ("8.0", "2026-04-24", [
        "重大: 新增量在价先维度（主力吸筹信号，权重15%）",
        "重大: 新增热点消息维度（消息面催化，权重15%）",
        "新增: 板块轮动加成（今日热点板块股票+15分）",
        "新增: 九维度评分体系（趋势/动量/左侧/量价/量在价先/形态/位置/热点消息/情绪）",
        "固化: 实时数据失败时不降级日线模式",
        "固化: 股票名称实时获取机制",
    ]),
    ("7.4", "2026-04-24", [
        "强制: 实时数据失败时不降级到日线模式（覆盖率为0则阻止保存出击报告）",
        "修复: 股票名称获取优先使用实时/AKShare接口，移除对STOCK_NAMES的依赖",
        "修复: 持仓股票名称为空时调用_get_stock_name()获取正确名称",
    ]),
    ("7.3", "2026-04-24", [
        "固化: 实时数据覆盖率检查（<30%阻止保存，<50%警告，>50%成功）",
        "固化: 实时模式增加大盘趋势判断",
        "固化: 数据源标注（新浪/腾讯）",
    ]),
    ("7.2", "2026-04-22", [
        "固化: 实时数据规范（新浪/腾讯接口优先）",
        "固化: 追高过滤机制（BOLL>85%/RSI>70自动降级）",
        "固化: 纯左侧战法选股标准（RSI<35, BOLL 30-70%）",
        "固化: 成功案例与失败案例分析",
        "新增: 客户需求文档v7.2（核心规范）",
    ]),
    ("7.1", "2026-04-22", [
        "修复: 实时数据获取改用新浪实时接口（之前错误使用Tushare日线数据）",
        "修复: 选股评分增加追高过滤机制（BOLL>85%/RSI>70等自动降级）",
        "优化: 综合评分中加入BOLL位置、RSI、涨幅等多重追高检查",
    ]),
    ("7.0", "2026-04-21", [
        "重大: 强制实时选股，移除自动/盘后模式",
        "新增: 每次选股显示时间戳",
        "新增: 使用最新版本算法",
    ]),
    ("6.5", "2026-04-21", [
        "修复: 选股结果表格添加股票名称列，显示正确的实时名称",
        "修复: 修复了股票名称乱码问题（XDDR、创业板化学等错误名称）",
    ]),
]

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
    """选股命令 - 强制实时模式"""
    from datetime import datetime

    # 强制实时模式（7.0+）
    realtime_mode = True
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*50}")
    print(f"开始选股筛选... 【实时模式】")
    print(f"选股时间: {timestamp}")
    print(f"使用版本: v{VERSION}")
    print(f"{'='*50}\n")

    screener = get_screener()
    results = screener.screen(market=args.market, limit=args.limit, realtime=realtime_mode)

    if not results:
        print("未筛选出符合条件的股票")
        return

    # 检查是否为实时模式
    first_realtime = results[0].get('实时模式', False) if results else False

    print(f"\n筛选结果（共{len(results)}只，按评分排序）【实时数据】：\n")
    print(f"{'代码':<10} {'名称':<10} {'评级':<6} {'信号':<8} {'总分':<6} {'趋势':<6} {'动量':<6} {'量价':<6} {'量先':<6} {'热点':<6} {'情绪':<6} {'板块':<6}")
    print("-" * 130)

    for i, stock in enumerate(results[:args.limit], 1):
        code = stock.get('代码', '') or stock.get('code', '')
        name = stock.get('名称', '') or stock.get('name', '') or stock.get('股票名称', '') or code
        rating = stock.get('评级', 'B')
        signal = stock.get('信号', '持有')
        total = stock.get('总分', 0)
        trend = stock.get('趋势', 0) or stock.get('趋势分', 0)
        momentum = stock.get('动量', 0) or stock.get('动量分', 0)
        vol_price = stock.get('量价', 0) or stock.get('量价分', 0)
        vol_leading = stock.get('量在价先', 0)
        news_hot = stock.get('热点消息', 0)
        sentiment = stock.get('情绪', 0) or stock.get('情绪分', 0)
        sector = stock.get('所属板块', '') or stock.get('板块状态', '')

        print(f"{code:<10} {name:<10} {rating:<6} {signal:<8} {total:<6.1f} {trend:<6.1f} {momentum:<6.1f} {vol_price:<6.1f} {vol_leading:<6.1f} {news_hot:<6.1f} {sentiment:<6.1f} {sector:<6}")

    print()

    # ============================================================
    # 实时数据覆盖率检查（客户需求文档 v7.3 固化要求）
    # ============================================================
    stats = screener.get_last_screen_stats()
    save_blocked = False
    if stats and stats.get("realtime_mode"):
        candidates = stats.get("candidates", 0)
        spots = stats.get("spots_fetched", 0)
        coverage = spots / candidates * 100 if candidates > 0 else 0

        if coverage < 30:
            data_source = stats.get("data_source", "未知")
            print(f"\n{'='*50}")
            if spots == 0:
                print(f"【严重】实时数据获取完全失败（新浪/腾讯均不可用）")
                print(f"  候选股票: {candidates} 只")
                print(f"  成功获取实时数据: 0 只")
                print(f"  数据源: {data_source}")
                print(f"  → 本次选股未使用实时数据，不更新出击报告")
                print(f"  → 请检查网络后重新运行选股")
            else:
                print(f"【严重】实时数据获取失败率过高: {100-coverage:.1f}%")
                print(f"  候选股票: {candidates} 只")
                print(f"  成功获取实时数据: {spots} 只")
                print(f"  覆盖率: {coverage:.1f}%")
                print(f"  数据源: {data_source}")
                print(f"  → 本次选股数据不完整，不更新出击报告")
                print(f"  → 请检查网络后重新运行选股")
            print(f"{'='*50}\n")
            save_blocked = True
        elif coverage < 50:
            data_source = stats.get("data_source", "未知")
            print(f"\n{'='*50}")
            print(f"【警告】实时数据不稳定，部分失败")
            print(f"  候选股票: {candidates} 只")
            print(f"  成功获取实时数据: {spots} 只")
            print(f"  覆盖率: {coverage:.1f}%")
            print(f"  数据源: {data_source}")
            print(f"  → 建议：检查网络后重新运行选股以获得完整结果")
            print(f"{'='*50}\n")
        else:
            data_source = stats.get("data_source", "新浪/腾讯")
            print(f"\n[PASS] 实时数据：成功 ({spots}/{candidates} 只) - 数据源: {data_source}\n")

    # 保存结果到文件（仅在覆盖率>=30%时更新出击报告）
    tracker = get_tracker()

    if save_blocked:
        # 覆盖率<30%：不更新出击相关文件，只保留持仓检查
        print("\n【提示】仅更新持仓检查，暂不更新出击报告")
        tracker.add_weekly_watchlist(results)  # 持仓股票仍更新最新价格
        # tracker.save_weekly_watchlist(results)  # 不保存，避免污染周选池
        # tracker.save_report()  # 不保存出击报告
        holding_report = tracker.get_holding_report()
        print("\n" + holding_report)
        print(f"\n出击报告未更新（实时数据覆盖率仅{coverage:.1f}%，请重新运行）")
    else:
        tracker.add_weekly_watchlist(results)
        tracker.save_weekly_watchlist(results)

        # 先打印持仓检查报告（使用最新数据）
        holding_report = tracker.get_holding_report()
        print("\n" + holding_report)

        # 再生成出击报告（持仓股票信号已包含在出击.txt中）
        tracker.save_report()

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


def cmd_news(args):
    """消息面命令"""
    from data_fetcher import get_news_fetcher

    news_fetcher = get_news_fetcher()

    if not news_fetcher.is_available():
        print("AKShare未安装，消息面功能不可用")
        print("请运行: pip install akshare")
        return

    if args.subcommand == "general":
        # 市场快讯
        print(f"\n{'='*60}")
        print(f"A股市场快讯")
        print(f"{'='*60}\n")

        df = news_fetcher.get_general_news(limit=args.limit)

        if df is None or df.empty:
            print("暂无数据")
            return

        print(f"共 {len(df)} 条快讯：\n")
        for i, row in df.head(args.limit).iterrows():
            title = row.get('title', row.get('标题', ''))
            pub_time = row.get('pub_time', row.get('发布时间', ''))
            source = row.get('source', row.get('来源', ''))
            content = str(row.get('content', row.get('内容', '')))[:100]

            print(f"【{pub_time}】{title}")
            if content and content != 'nan':
                print(f"   {content}...")
            print()

    elif args.subcommand == "stock":
        # 个股新闻
        symbol = args.symbol.strip()
        print(f"\n{'='*60}")
        print(f"个股新闻: {symbol}")
        print(f"{'='*60}\n")

        df = news_fetcher.get_stock_news(symbol)

        if df is None or df.empty:
            print("暂无数据")
            return

        print(f"共 {len(df)} 条新闻：\n")
        for i, row in df.iterrows():
            title = row.get('title', row.get('标题', ''))
            pub_time = row.get('pub_time', row.get('发布时间', ''))
            content = str(row.get('content', row.get('内容', '')))[:150]

            print(f"【{pub_time}】{title}")
            if content and content != 'nan':
                print(f"   {content}...")
            print()

    elif args.subcommand == "sentiment":
        # 情绪分析
        symbol = args.symbol.strip()
        print(f"\n{'='*60}")
        print(f"消息面情绪分析: {symbol}")
        print(f"{'='*60}\n")

        result = news_fetcher.analyze_sentiment(symbol)

        print(f"情绪评分: {result['score']}/100")
        print(f"信号: 【{result['signal']}】")
        print(f"新闻数量: {result['news_count']}")
        print(f"公告数量: {result['ann_count']}")
        print(f"涨停: {'是 ✓' if result['limit_up'] else '否'}")

        if result['keywords']:
            print(f"\n利好因素 ({len(result['keywords'])}):")
            for kw in result['keywords'][:10]:
                print(f"  ✓ {kw}")

        if result['risk_keywords']:
            print(f"\n风险因素 ({len(result['risk_keywords'])}):")
            for kw in result['risk_keywords'][:10]:
                print(f"  ✗ {kw}")

        print(f"\n摘要: {result['summary']}")
        print()


def cmd_announcement(args):
    """公告命令"""
    from data_fetcher import get_news_fetcher

    news_fetcher = get_news_fetcher()

    if not news_fetcher.is_available():
        print("AKShare未安装，公告功能不可用")
        return

    symbol = args.symbol.strip() if args.symbol else None
    date = args.date

    print(f"\n{'='*60}")
    print(f"公告查询: {symbol or '全市场'} | 日期: {date}")
    print(f"{'='*60}\n")

    df = news_fetcher.get_announcement(symbol=symbol, date=date, limit=args.limit)

    if df is None or df.empty:
        print("暂无数据")
        return

    print(f"共 {len(df)} 条公告：\n")

    # 按股票分组显示
    grouped = {}
    for _, row in df.iterrows():
        name = row.get('name', row.get('ts_code', '未知'))
        title = row.get('title', '无标题')
        ann_time = row.get('ann_time', '')
        ann_type = row.get('ann_type', '')

        if name not in grouped:
            grouped[name] = []
        grouped[name].append((ann_time, ann_type, title))

    for name, announcements in list(grouped.items())[:20]:
        print(f"【{name}】")
        for ann_time, ann_type, title in announcements[:5]:
            print(f"  [{ann_time}] [{ann_type}] {title}")
        if len(announcements) > 5:
            print(f"  ... 还有 {len(announcements) - 5} 条公告")
        print()

    if len(grouped) > 20:
        print(f"... 还有 {len(grouped) - 20} 只股票的公告未显示")


def cmd_limit_up(args):
    """涨跌停原因命令"""
    from data_fetcher import get_news_fetcher

    news_fetcher = get_news_fetcher()

    if not news_fetcher.is_available():
        print("AKShare未安装，涨跌停功能不可用")
        return

    date = args.date
    limit_type = args.type  # 'up' or 'down'

    print(f"\n{'='*60}")
    print(f"涨跌停原因追踪 | 日期: {date} | 类型: {'涨停' if limit_type == 'up' else '跌停'}")
    print(f"{'='*60}\n")

    if limit_type == "up":
        df = news_fetcher.get_limit_up_reason(trade_date=date)
    else:
        df = news_fetcher.get_limit_down_reason(trade_date=date)

    if df is None or df.empty:
        print("暂无数据")
        return

    print(f"共 {len(df)} 只{'涨' if limit_type == 'up' else '跌'}停股票：\n")

    # 按原因分类
    reason_groups = {}
    for _, row in df.iterrows():
        reason = str(row.get('reason', row.get('涨停原因', '其他')))
        if reason not in reason_groups:
            reason_groups[reason] = []
        reason_groups[reason].append(row)

    # 显示原因分类
    for reason, stocks in sorted(reason_groups.items(), key=lambda x: -len(x[1])):
        print(f"\n【{reason}】- {len(stocks)} 只")
        print("-" * 50)

        for row in stocks[:10]:
            name = row.get('name', row.get('名称', ''))
            code = str(row.get('ts_code', row.get('代码', ''))).replace(".sh", "").replace(".sz", "")
            limit_stat = str(row.get('limit_stat', row.get('涨停统计', '-')))
            limit_time = str(row.get('limit_time', row.get('涨停时间', '-')))

            if limit_type == "up":
                print(f"  {code} {name:<10} | {limit_stat:<10} | {limit_time}")
            else:
                print(f"  {code} {name:<10}")

        if len(stocks) > 10:
            print(f"  ... 还有 {len(stocks) - 10} 只")


def show_version():
    """显示版本信息"""
    print(f"╔══════════════════════════════════════════╗")
    print(f"║         小金库 Stock System v{VERSION}        ║")
    print(f"╚══════════════════════════════════════════╝")
    print()
    # 显示最新版本更新
    if VERSION_LOG:
        latest_ver, latest_date, latest_changes = VERSION_LOG[0]
        print(f"【v{latest_ver} 更新】 ({latest_date})")
        for change in latest_changes:
            print(f"  - {change}")
        print()
        print("（查看完整更新记录: --changelog 或 -c）")
        print()


def main():
    # 解析参数先检查是否有 --changelog
    if "--changelog" in sys.argv or "-c" in sys.argv:
        show_version()
        sys.exit(0)

    # 显示版本信息
    show_version()

    parser = argparse.ArgumentParser(description="股票分析系统")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--changelog", "-c", action="store_true", help="显示版本更新记录")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 选股命令（7.0+ 强制实时模式）
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

    # 消息面命令
    parser_news = subparsers.add_parser("news", help="消息面查询")
    subparsers_news = parser_news.add_subparsers(dest="subcommand", help="消息面子命令")
    parser_news_general = subparsers_news.add_parser("general", help="市场快讯")
    parser_news_general.add_argument("--limit", "-l", type=int, default=30, help="返回条数")

    parser_news_stock = subparsers_news.add_parser("stock", help="个股新闻")
    parser_news_stock.add_argument("symbol", help="股票代码")

    parser_news_sentiment = subparsers_news.add_parser("sentiment", help="情绪分析")
    parser_news_sentiment.add_argument("symbol", help="股票代码")

    # 公告命令
    parser_ann = subparsers.add_parser("announcement", help="公告查询")
    parser_ann.add_argument("--symbol", "-s", help="股票代码，默认为全市场")
    parser_ann.add_argument("--date", "-d", default=None, help="日期 YYYYMMDD")
    parser_ann.add_argument("--limit", "-l", type=int, default=50, help="返回条数")

    # 涨跌停原因命令
    parser_limit = subparsers.add_parser("limit-up", help="涨跌停原因追踪")
    parser_limit.add_argument("--type", "-t", choices=["up", "down"], default="up", help="类型: up=涨停, down=跌停")
    parser_limit.add_argument("--date", "-d", default=None, help="日期 YYYYMMDD")

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
    elif args.command == "news":
        cmd_news(args)
    elif args.command == "announcement":
        cmd_announcement(args)
    elif args.command == "limit-up":
        cmd_limit_up(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
