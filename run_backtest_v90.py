"""
小金库 9.0 完整回测对比 - Step 3b 验证脚本

跑 4 种组合对比 v8.x 基线 vs v9.0 完整版：
- (False, False) = v8.x 基线（5维度，无右侧确认）
- (True, False)  = 仅加新维度（基本面/资金面/催化剂）
- (False, True)  = 仅加观察池右侧确认
- (True, True)   = v9.0 完整版

输出：
- View Results/9.0回测报告.txt（人类可读对比表）
- View Results/9.0回测.json（结构化结果）

注意：
- 基本面/资金面数据接口当前只能拿最新数据，回测中用最新数据近似历史
- 这是 lookahead bias，结果应作为"上限参考"而非真实表现
"""
import sys
import os
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

# 强制 stdout 行缓冲（确保进度日志实时刷新）
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

sys.path.insert(0, 'stocks/Stock Selection')

from backtester import Backtester

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ========== 50 只沪深 300 权重股（覆盖大盘 + 多行业） ==========
STOCK_POOL_50 = [
    # 白酒消费
    "600519", "000858", "600887", "603288", "600600",
    # 金融
    "601318", "601398", "600036", "600030", "601628",
    # 科技
    "002415", "000725", "002230", "002475", "300750",
    # 医药
    "600276", "300015", "000661", "002007", "600196",
    # 新能源
    "601012", "300750", "002460", "600438", "002129",
    # 周期
    "601857", "600028", "600585", "601668", "601899",
    # 地产基建
    "000002", "600048", "601800", "601186", "600009",
    # 家电
    "000333", "000651", "600690", "002508", "002032",
    # 通信网络
    "002594", "002241", "600050", "600487", "601728",
    # 大盘指标
    "000001", "601888", "600900", "600276", "601628",
]
# 去重
STOCK_POOL_50 = list(dict.fromkeys(STOCK_POOL_50))[:50]


# ========== 4 种回测组合 ==========
CONFIGS = [
    {"name": "v8.x 基线",       "use_v90_dimensions": False, "use_observation_pool": False},
    {"name": "仅加新维度",       "use_v90_dimensions": True,  "use_observation_pool": False},
    {"name": "仅加观察池",       "use_v90_dimensions": False, "use_observation_pool": True},
    {"name": "v9.0 完整版",     "use_v90_dimensions": True,  "use_observation_pool": True},
]


def run_one_config(config, start_date, end_date, stock_pool, init_capital=1_000_000):
    """跑单个配置组合"""
    print(f"\n{'='*70}", flush=True)
    print(f"配置: {config['name']} | dim={config['use_v90_dimensions']} obs={config['use_observation_pool']}", flush=True)
    print(f"{'='*70}", flush=True)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始拉数据 + 评分 + 模拟交易...", flush=True)

    bt = Backtester(initial_capital=init_capital)
    stats = bt.run(
        start_date=start_date,
        end_date=end_date,
        stock_pool=stock_pool,
        strategy="left",
        stop_loss=0.08,
        take_profit=0.20,
        position_size=0.10,
        use_v90_dimensions=config["use_v90_dimensions"],
        use_observation_pool=config["use_observation_pool"],
    )
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 配置完成", flush=True)
    bt.print_report(stats)
    return stats, bt.trades


def render_comparison_report(all_results, start_date, end_date, stock_pool):
    """生成 4 配置对比报告（人类可读）"""
    lines = []
    lines.append("=" * 80)
    lines.append("小金库 9.0 回测对比报告 (Step 3b)")
    lines.append("=" * 80)
    lines.append(f"回测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"回测区间: {start_date} ~ {end_date}")
    lines.append(f"股票池:   {len(stock_pool)} 只 (沪深 300 权重股)")
    lines.append(f"参数:     止损 8% / 止盈 20% / 单次仓位 10% / 初始 100 万")
    lines.append("")
    lines.append("[!] Note: Fundamentals/MoneyFlow/Catalyst data interfaces only return latest data.")
    lines.append("    Backtest uses latest data as historical approximation (lookahead bias).")
    lines.append("    Results should be treated as 'upper bound reference' rather than real performance.")
    lines.append("")
    lines.append("=" * 80)
    lines.append("4 种组合对比")
    lines.append("=" * 80)
    lines.append(
        f"{'配置':<14} {'交易数':>6} {'胜率':>7} {'总收益':>9} {'年化':>9} "
        f"{'最大回撤':>9} {'夏普':>7} {'平均持仓':>9}"
    )
    lines.append("-" * 80)

    for cfg, stats in zip(CONFIGS, all_results):
        lines.append(
            f"{cfg['name']:<14} "
            f"{stats['交易次数']:>6} "
            f"{stats['胜率']*100:>6.1f}% "
            f"{stats['总收益率']:>8.1f}% "
            f"{stats['年化收益率']:>8.1f}% "
            f"{stats['最大回撤']:>8.1f}% "
            f"{stats['夏普比率']:>7.2f} "
            f"{stats['平均持仓天数']:>7.1f}d"
        )

    lines.append("=" * 80)
    lines.append("")
    lines.append("结论参考（不是绝对值，看相对趋势）：")
    base = all_results[0]
    full = all_results[3]
    lines.append(f"  v9.0 完整版 vs v8.x 基线：")
    if base['交易次数'] > 0 and full['交易次数'] > 0:
        lines.append(f"    胜率变化:    {(full['胜率']-base['胜率'])*100:+.1f}%")
        lines.append(f"    总收益变化:  {full['总收益率']-base['总收益率']:+.1f}%")
        lines.append(f"    最大回撤变化: {full['最大回撤']-base['最大回撤']:+.1f}% (负数=改善)")
        lines.append(f"    夏普变化:    {full['夏普比率']-base['夏普比率']:+.2f}")
    else:
        lines.append("    交易次数过少（< 1），结论无意义")
    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="小金库 9.0 完整回测对比")
    parser.add_argument("--quick", action="store_true",
                        help="冒烟测试模式（5 只股票 × 1 个月 × 1 个配置）")
    parser.add_argument("--start", default="20240507", help="起始日期 YYYYMMDD")
    parser.add_argument("--end", default="20260507", help="结束日期 YYYYMMDD")
    parser.add_argument("--config", default="all",
                        choices=["all", "baseline", "dim", "obs", "v90"],
                        help="只跑指定配置（默认全部 4 个）")
    args = parser.parse_args()

    if args.quick:
        print("[QUICK MODE] Smoke test")
        stock_pool = STOCK_POOL_50[:5]
        start_date = "20260101"
        end_date = "20260201"
        # quick 模式默认跑 v9.0 完整版，但允许 --config 覆盖
        if args.config == "all":
            configs_to_run = [CONFIGS[3]]  # 只跑 v9.0 完整版
        else:
            idx_map = {"baseline": 0, "dim": 1, "obs": 2, "v90": 3}
            configs_to_run = [CONFIGS[idx_map[args.config]]]
    else:
        stock_pool = STOCK_POOL_50
        start_date = args.start
        end_date = args.end
        if args.config == "all":
            configs_to_run = CONFIGS
        else:
            idx_map = {"baseline": 0, "dim": 1, "obs": 2, "v90": 3}
            configs_to_run = [CONFIGS[idx_map[args.config]]]

    print(f"\n股票池: {len(stock_pool)} 只")
    print(f"区间:   {start_date} ~ {end_date}")
    print(f"配置数: {len(configs_to_run)}")
    print()

    all_results = []
    all_trades = {}
    for config in configs_to_run:
        stats, trades = run_one_config(config, start_date, end_date, stock_pool)
        all_results.append(stats)
        all_trades[config["name"]] = [
            {
                "code": t["code"],
                "buy_date": t["buy_date"],
                "buy_price": t["buy_price"],
                "sell_price": t["sell_price"],
                "sell_reason": t["sell_reason"],
                "profit_pct": round(t["profit_pct"] * 100, 2),
                "hold_days": t["hold_days"],
            }
            for t in trades
        ]

    # 输出报告
    output_dir = Path("stocks/Stock Selection/View Results")
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.quick:
        report_path = output_dir / "9.0回测报告_quick.txt"
        json_path = output_dir / "9.0回测_quick.json"
    else:
        # 单配置或完整对比都保存到同一个文件
        json_path = output_dir / "9.0回测.json"
        if len(configs_to_run) == 4:
            report_path = output_dir / "9.0回测报告.txt"
            report = render_comparison_report(all_results, start_date, end_date, stock_pool)
            print()
            print(report)
            report_path.write_text(report, encoding="utf-8")

    # JSON 备份
    json_data = {
        "回测时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "区间": f"{start_date} ~ {end_date}",
        "股票池": stock_pool,
        "股票数": len(stock_pool),
        "结果": [
            {"配置": cfg["name"], "use_v90_dimensions": cfg["use_v90_dimensions"],
             "use_observation_pool": cfg["use_observation_pool"], "stats": stats}
            for cfg, stats in zip(configs_to_run, all_results)
        ],
        "交易明细": all_trades,
    }
    with open(str(json_path), 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Reports saved:")
    if not args.quick and len(configs_to_run) == 4:
        print(f"   {report_path}")
    print(f"   {json_path}")


if __name__ == "__main__":
    main()
