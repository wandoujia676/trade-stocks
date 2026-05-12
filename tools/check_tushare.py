"""
Tushare 接口诊断脚本
用法：python tools/check_tushare.py

依次测试 daily/moneyflow/hk_hold/margin_detail/forecast/stk_surv 接口：
- 打印每个接口：状态 / 返回行数 / 耗时 / 失败原因
- 根据诊断结果给出三档决策建议（交互式）
"""
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "stocks" / "Stock Selection"))

try:
    import config as stock_config
except ImportError as e:
    print(f"❌ 无法导入 config.py: {e}")
    print(f"   PROJECT_ROOT = {PROJECT_ROOT}")
    sys.exit(1)

try:
    import tushare as ts
except ImportError:
    print("❌ 未安装 tushare，请先 pip install tushare")
    sys.exit(1)


TEST_CODE = "000001.SZ"
TEST_START = "20260501"
TEST_END = "20260510"
TEST_TRADE_DATE = "20260509"

INTERFACES = [
    {
        "name": "daily",
        "desc": "日线行情",
        "dimension": "技术面",
        "call": lambda pro: pro.daily(ts_code=TEST_CODE, start_date=TEST_START, end_date=TEST_END),
    },
    {
        "name": "moneyflow",
        "desc": "主力资金流",
        "dimension": "资金面（核心）",
        "call": lambda pro: pro.moneyflow(ts_code=TEST_CODE, trade_date=TEST_TRADE_DATE),
    },
    {
        "name": "hk_hold",
        "desc": "北向持股",
        "dimension": "资金面",
        "call": lambda pro: pro.hk_hold(ts_code=TEST_CODE, start_date=TEST_START, end_date=TEST_END),
    },
    {
        "name": "margin_detail",
        "desc": "融资融券明细",
        "dimension": "资金面",
        "call": lambda pro: pro.margin_detail(ts_code=TEST_CODE, trade_date=TEST_TRADE_DATE),
    },
    {
        "name": "forecast",
        "desc": "业绩预告",
        "dimension": "催化剂（核心）",
        "call": lambda pro: pro.forecast(ts_code=TEST_CODE, start_date="20260101", end_date=TEST_END),
    },
    {
        "name": "stk_surv",
        "desc": "机构调研",
        "dimension": "催化剂",
        "call": lambda pro: pro.stk_surv(ts_code=TEST_CODE, start_date="20260101", end_date=TEST_END),
    },
]


def classify_error(err_msg: str) -> str:
    s = err_msg.lower()
    if "积分" in err_msg or "points" in s or "权限" in err_msg or "permission" in s:
        return "权限不足"
    if "token" in s or "无效" in err_msg or "expired" in s:
        return "token 无效"
    if "频率" in err_msg or "frequency" in s or "limit" in s or "rate" in s:
        return "频率超限"
    if "connection" in s or "timeout" in s or "remotedisconnected" in s:
        return "网络错误"
    return "未知错误"


def probe(pro) -> list:
    results = []
    for it in INTERFACES:
        t0 = time.time()
        try:
            df = it["call"](pro)
            elapsed = time.time() - t0
            rows = len(df) if df is not None else 0
            results.append({
                **it,
                "status": "✅ 通",
                "rows": rows,
                "elapsed": elapsed,
                "error": None,
                "category": None,
            })
        except Exception as e:
            elapsed = time.time() - t0
            err_str = str(e)
            results.append({
                **it,
                "status": "❌ 失败",
                "rows": 0,
                "elapsed": elapsed,
                "error": err_str,
                "category": classify_error(err_str),
            })
    return results


def print_matrix(results: list):
    print()
    print("┌────────────────┬─────────────────┬───────────┬──────────┬──────────────────────┐")
    print("│ 接口           │ 维度             │ 状态      │ 耗时     │ 说明                  │")
    print("├────────────────┼─────────────────┼───────────┼──────────┼──────────────────────┤")
    for r in results:
        name = r["name"].ljust(14)
        dim = r["dimension"].ljust(14 - (len(r["dimension"].encode("gbk", errors="ignore")) - len(r["dimension"])))
        status = r["status"].ljust(8)
        elapsed = f"{r['elapsed']:.2f}s".ljust(8)
        if r["error"] is None:
            msg = f"{r['rows']} 行"
        else:
            msg = f"{r['category']}: {r['error'][:30]}"
        print(f"│ {name} │ {r['dimension']:<14} │ {status} │ {elapsed} │ {msg:<20} │")
    print("└────────────────┴─────────────────┴───────────┴──────────┴──────────────────────┘")
    print()


def interactive_decide(results: list):
    by_name = {r["name"]: r for r in results}
    daily_ok = by_name["daily"]["error"] is None
    moneyflow_ok = by_name["moneyflow"]["error"] is None
    forecast_ok = by_name["forecast"]["error"] is None

    print("=" * 70)
    print("决策建议")
    print("=" * 70)

    if daily_ok and moneyflow_ok and forecast_ok:
        print("✅ 情况 A：三项核心接口（daily + moneyflow + forecast）全通")
        print()
        print("   建议切换 config.py:47")
        print("     DATA_SOURCE_PRIORITY = ['tushare', 'akshare']")
        print()
        print("   这样可以完全绕开东财反爬问题。")
        return "A"

    if daily_ok and not (moneyflow_ok and forecast_ok):
        missing = []
        if not moneyflow_ok:
            missing.append(f"moneyflow ({by_name['moneyflow']['category']})")
        if not forecast_ok:
            missing.append(f"forecast ({by_name['forecast']['category']})")
        print("⚠️  情况 B：日线可用，但核心高阶接口不可用")
        print(f"   不可用接口：{', '.join(missing)}")
        print("   资金面(8%) + 催化剂(7%) 共 15% 权重在 Tushare 路径上拿不到")
        print()
        print("   选项：")
        print("   [1] 去充积分或做任务刷积分")
        print("       - 免费：登录+实名+完善资料 ≈ 500 分")
        print("       - VIP：200~500 元/年 → 5000 分")
        print("       - 充完回车，脚本会重新检测")
        print("   [2] 不充，保持 AKShare 优先 + 重试方案")
        print("       这两个维度遇东财反爬时给中性 50 分")
        print("   [3] 退出，稍后手动决定")
        print()
        choice = input("请选择 (1/2/3): ").strip()
        return f"B-{choice}"

    print("❌ 情况 C：daily 接口不通")
    print(f"   失败原因：{by_name['daily']['category']}")
    print(f"   错误详情：{by_name['daily']['error']}")
    print()
    if by_name["daily"]["category"] == "token 无效":
        print("   建议：")
        print("   - 检查 config.py:38 的 TUSHARE_TOKEN 是否失效")
        print("   - 去 https://tushare.pro/user/token 看账号 token")
    else:
        print("   建议：")
        print("   - 检查网络（Tushare 服务器是否可达）")
        print("   - 稍后重试")
    print()
    print("   本次维持 AKShare 优先 + 重试方案，不切数据源")
    return "C"


def main():
    print("=" * 70)
    print("Tushare 接口诊断")
    print("=" * 70)

    token = stock_config.TUSHARE_TOKEN
    if not token:
        print("❌ config.py 中 TUSHARE_TOKEN 为空")
        sys.exit(1)
    print(f"Token: {token[:8]}...{token[-4:]} (前8后4)")
    print(f"测试代码: {TEST_CODE}")
    print(f"测试区间: {TEST_START} ~ {TEST_END}")
    print()

    try:
        ts.set_token(token)
        pro = ts.pro_api()
    except Exception as e:
        print(f"❌ Tushare 初始化失败: {e}")
        sys.exit(1)

    print("开始测试 6 个接口...\n")

    while True:
        results = probe(pro)
        print_matrix(results)
        decision = interactive_decide(results)

        if decision == "B-1":
            input("\n👉 去 https://tushare.pro 充完积分/完善资料后，按回车继续重新检测...\n")
            continue
        break

    print()
    print("=" * 70)
    print(f"最终决策码: {decision}")
    print("=" * 70)


if __name__ == "__main__":
    main()
