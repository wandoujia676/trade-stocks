"""
三层候选池一次性生成脚本
每月15号和28号下午2点执行

一次性完成三层筛选：
1. monthly_watchlist（约100只）- 从全市场5000+只筛选
2. weekly_watchlist（约20只）- 从monthly中六维度战法评分
3. 出击（约5只）- 从weekly中精选
"""
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def main():
    print("="*60)
    print(f"三层候选池生成任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    try:
        # ========== 第一层：月度候选股票池 ==========
        print("\n【第一层】生成月度候选股票池...")
        from monthly_generator import MonthlyGenerator

        generator = MonthlyGenerator()
        monthly_stocks = generator.screen(target_count=100)

        if monthly_stocks:
            output_dir = Path(__file__).parent / "View Results"
            generator.save_result(monthly_stocks, output_dir)
            print(f"月度候选股票池生成完成！共 {len(monthly_stocks)} 只")
        else:
            print("\n月度候选股票池生成失败，请检查日志")
            return

        # ========== 第二层：周选股票池 ==========
        print("\n【第二层】生成周选股票池...")
        from screener import get_screener
        from selection_tracker import get_tracker

        screener = get_screener()
        weekly_stocks = screener.screen(market="全市场", limit=20)

        if weekly_stocks:
            # 保存到JSON文件
            output_dir = Path(__file__).parent / "View Results"
            output_file = output_dir / "weekly_watchlist.json"

            watchlist = []
            for stock in weekly_stocks:
                watchlist.append({
                    "code": stock.get("code", ""),
                    "rating": stock.get("评级", "B"),
                    "signal": stock.get("信号", "持有"),
                    "score": stock.get("总分", 0),
                    "price": stock.get("最新价", 0),
                    "change": stock.get("涨跌幅", 0),
                    "selected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "reasons": stock.get("理由", [])
                })

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(watchlist, f, ensure_ascii=False, indent=2)

            # 保存到选股跟踪器（生成出击.txt等）
            tracker = get_tracker()
            tracker.add_weekly_watchlist(weekly_stocks)
            tracker.save_weekly_watchlist(weekly_stocks)
            tracker.save_report()

            # 过滤出加仓信号单独记录
            buy_signals = ["加仓", "买入", "强烈推荐"]
            buy_stocks = [s for s in weekly_stocks if s.get("信号", "") in buy_signals]
            if buy_stocks:
                tracker.add_buy_signal(buy_stocks)

            print(f"周选股票池生成完成！共 {len(weekly_stocks)} 只")

            # 打印摘要
            print("\n" + "="*60)
            print("周选股票池摘要")
            print("="*60)
            print(f"{'代码':<10} {'评级':<6} {'信号':<8} {'评分':<6}")
            print("-"*40)
            for stock in weekly_stocks[:10]:
                print(f"{stock['code']:<10} {stock.get('评级','B'):<6} {stock.get('信号','持有'):<8} {stock.get('总分',0):<6.1f}")

            # 打印出击股票
            buyable = [s for s in weekly_stocks if s.get("信号", "") in buy_signals and s.get("总分", 0) >= 65]
            if buyable:
                print("\n" + "="*60)
                print(f"【出击股票】共 {len(buyable)} 只")
                print("="*60)
                for stock in buyable:
                    print(f"  {stock['code']} - {stock.get('评级','B')} - {stock.get('信号','持有')} (评分{stock.get('总分',0):.1f})")
        else:
            print("\n周选股票池生成失败")

        print(f"\n三层候选池生成全部完成！")
        print(f"输出目录: {output_dir}")

    except Exception as e:
        logging.error(f"三层候选池生成失败: {e}")
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print(f"任务结束 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)


if __name__ == "__main__":
    main()
