"""
自动选股脚本 - 每周定时执行
生成自选股列表并保存
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    # 添加项目路径
    sys.path.insert(0, str(Path(__file__).parent))

    from screener import get_screener
    from data_fetcher import get_fetcher
    from selection_tracker import get_tracker

    print("="*60)
    print(f"自动选股任务开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    try:
        # 执行选股
        screener = get_screener()
        results = screener.screen(market="全市场", limit=20)

        if results:
            # 保存到JSON文件
            output_dir = Path(__file__).parent / "View Results"
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / "weekly_watchlist.json"

            watchlist = []
            for stock in results:
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

            # 记录到选股跟踪器
            tracker = get_tracker()
            tracker.add_weekly_watchlist(results)
            tracker.save_weekly_watchlist(results)
            tracker.save_report()

            # 过滤出加仓信号单独记录
            buy_signals = ["加仓", "买入", "强烈推荐"]
            buy_stocks = [s for s in results if s.get("信号", "") in buy_signals]
            if buy_stocks:
                tracker.add_buy_signal(buy_stocks)

            print(f"\n选股完成！选出 {len(watchlist)} 只股票")
            print(f"结果已保存到: {output_file}")

            # 打印摘要
            print("\n" + "="*60)
            print("本周自选股摘要")
            print("="*60)
            print(f"{'代码':<10} {'评级':<6} {'信号':<8} {'评分':<6} {'价格':<10} {'涨跌幅':<10}")
            print("-"*60)
            for stock in watchlist:
                print(f"{stock['code']:<10} {stock['rating']:<6} {stock['signal']:<8} {stock['score']:<6.1f} {stock['price']:<10.2f} {stock['change']:>+8.2f}%")

            # 打印加仓股票
            if buy_stocks:
                print("\n" + "="*60)
                print("加仓信号股票")
                print("="*60)
                for stock in buy_stocks:
                    print(f"  {stock['code']} - {stock['信号']} (评分{stock['总分']:.1f})")

        else:
            print("\n未筛选出符合条件的股票")

    except Exception as e:
        logging.error(f"自动选股失败: {e}")
        print(f"错误: {e}")

    print("\n" + "="*60)
    print(f"任务结束 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

if __name__ == "__main__":
    main()
