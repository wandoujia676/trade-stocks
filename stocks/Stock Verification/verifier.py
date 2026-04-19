"""
选股验证引擎
验证 skill_sel 前一日选股的成功率，并自动优化战法权重
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 全局 auto 模式标记
AUTO_MODE = False
FORCE_MODE = False

# 添加父目录到路径，以便导入 Stock Selection 模块
import importlib.util
PARENT_DIR = Path(__file__).parent.parent
SELECTION_DIR = PARENT_DIR / "Stock Selection"
sys.path.insert(0, str(SELECTION_DIR))

# 使用 importlib 动态导入（处理目录名含空格的情况）
def import_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

data_fetcher = import_from_path("data_fetcher", SELECTION_DIR / "data_fetcher.py")
config_module = import_from_path("config", SELECTION_DIR / "config.py")
DATA_DIR = config_module.DATA_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 路径配置
BASE_DIR = PARENT_DIR / "Stock Verification"
PICKS_FILE = PARENT_DIR / "Stock Selection" / "View Results" / "出击.txt"
VER_HISTORY_FILE = BASE_DIR / "ver_history.json"
WARFARE_CONFIG_FILE = BASE_DIR / "warfare_config.json"
VER_REPORT_FILE = BASE_DIR / "ver.txt"

# 战法维度权重配置
DEFAULT_WEIGHTS = {
    "趋势": 0.25,
    "动量": 0.15,
    "左侧": 0.15,
    "量价": 0.15,
    "形态": 0.15,
    "位置": 0.10,
    "情绪": 0.05,
}

# 权重调整阈值
SUCCESS_THRESHOLD_HIGH = 0.70  # 成功率 > 70% → +5%
SUCCESS_THRESHOLD_LOW = 0.40   # 成功率 < 40% → -5%
WEIGHT_ADJUSTMENT = 0.05
WEIGHT_MAX = 0.30
WEIGHT_MIN = 0.15

# 维度映射关键词
DIMENSION_KEYWORDS = {
    "趋势": ["均线多头", "MA多头", "上升趋势", "均线多头排列", "多头排列"],
    "动量": ["MACD强势", "MACD金叉", "MACD走强", "动量强", "KDJ金叉"],
    "左侧": ["超跌", "RSI", "左侧", "BOLL下轨", "负乖离", "左侧买入", "左侧超跌反弹"],
    "量价": ["放量", "量比放大", "缩量", "量价配合", "持续放量"],
    "形态": ["突破新高", "锤子线", "大阳线", "早晨之星", "K线形态", "突破"],
    "位置": ["BOLL", "boll", "位置", "上轨", "下轨", "中轨"],
    "情绪": ["涨停基因", "板块", "情绪", "涨停", "热门"],
}


def load_picks():
    """加载出击.txt数据"""
    if not PICKS_FILE.exists():
        return None

    with open(PICKS_FILE, 'r', encoding='utf-8') as f:
        picks_data = json.load(f)

    return picks_data


def has_new_picks():
    """检查出击股票是否有新内容（内容变化就算新）"""
    if not PICKS_FILE.exists():
        return False

    # 读取当前出击股票的代码列表
    with open(PICKS_FILE, 'r', encoding='utf-8') as f:
        picks = json.load(f)
    current_stocks = picks.get("出击股票", [])
    current_codes = set(s.get("代码", "") for s in current_stocks)

    # 读取上次验证记录的股票代码列表
    if not VER_HISTORY_FILE.exists():
        return True  # 首次运行，直接验证

    with open(VER_HISTORY_FILE, 'r', encoding='utf-8') as f:
        history = json.load(f)

    verifications = history.get("verifications", [])
    if not verifications:
        return True  # 无历史记录，首次验证

    last_ver = verifications[-1]
    last_codes = set(s.get("code", "") for s in last_ver.get("stocks", []))

    # 对比内容是否变化
    return current_codes != last_codes


def load_ver_history():
    """加载历史验证记录"""
    if not VER_HISTORY_FILE.exists():
        return {"verifications": [], "dimension_stats": {}}

    with open(VER_HISTORY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_ver_history(history):
    """保存历史验证记录"""
    with open(VER_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def load_warfare_config():
    """加载战法权重配置"""
    if not WARFARE_CONFIG_FILE.exists():
        # 创建默认配置
        config = {
            "weights": DEFAULT_WEIGHTS.copy(),
            "dimension_stats": {dim: {"success": 0, "fail": 0} for dim in DEFAULT_WEIGHTS},
            "last_updated": ""
        }
        save_warfare_config(config)
        return config

    with open(WARFARE_CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_warfare_config(config):
    """保存战法权重配置"""
    with open(WARFARE_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_realtime_data(code):
    """获取股票实时/日线数据用于验证"""
    try:
        fetcher = data_fetcher.get_fetcher()
        # 使用 get_daily 获取近2日数据来计算涨跌幅
        df = fetcher.get_daily(code, use_cache=False)

        if df is None or len(df) < 2:
            return None

        # 最新一天的数据
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # 计算涨跌幅（今日收盘 vs 昨日收盘）
        latest_price = float(latest.get("close", 0))
        prev_price = float(prev.get("close", 0))
        if prev_price > 0:
            change_pct = (latest_price - prev_price) / prev_price * 100
        else:
            change_pct = 0

        # 计算量比（今日成交量 / 昨日成交量）
        latest_vol = float(latest.get("volume", 0))
        prev_vol = float(prev.get("volume", 0))
        volume_ratio = latest_vol / prev_vol if prev_vol > 0 else 0

        return {
            "code": code,
            "name": "",  # 名称从选股数据获取
            "price": latest_price,
            "change_pct": change_pct,
            "volume_ratio": volume_ratio,
            "source": latest.get("source", "unknown"),
        }
    except Exception as e:
        logger.error(f"获取 {code} 数据失败: {e}")
        return None


def evaluate_stock(stock, realtime_data, picks_date):
    """评估单只股票的表现"""
    if not realtime_data:
        return {
            "code": stock.get("代码", ""),
            "name": stock.get("名称", ""),
            "score": stock.get("评分", 0),
            "signal": stock.get("信号", ""),
            "pick_price": stock.get("最新价", 0),
            "today_price": 0,
            "change_pct": 0,
            "result": "数据获取失败",
            "reason": "",
            "dimensions": []
        }

    code = stock.get("代码", "")
    today_change = realtime_data.get("change_pct", 0)

    # 判定成功/失败
    if today_change > 0:
        result = "成功"
    elif today_change < 0:
        result = "失败"
    else:
        result = "平盘"

    # 提取维度
    reasons = stock.get("理由", [])
    dimensions = extract_dimensions(reasons)

    # 生成分析原因
    reason = analyze_reason(stock, realtime_data, result, dimensions)

    return {
        "code": code,
        "name": realtime_data.get("name", stock.get("名称", "")),
        "score": stock.get("评分", 0),
        "signal": stock.get("信号", ""),
        "pick_price": stock.get("最新价", 0),
        "today_price": realtime_data.get("price", 0),
        "change_pct": today_change,
        "result": result,
        "reason": reason,
        "dimensions": dimensions,
        "pick_reasons": reasons
    }


def extract_dimensions(reasons):
    """从理由中提取涉及的维度"""
    dimensions = []
    for reason in reasons:
        for dim, keywords in DIMENSION_KEYWORDS.items():
            if any(kw in reason for kw in keywords):
                if dim not in dimensions:
                    dimensions.append(dim)
    return dimensions


def analyze_reason(stock, realtime_data, result, dimensions):
    """分析成功或失败的原因"""
    today_change = realtime_data.get("change_pct", 0)
    volume_ratio = realtime_data.get("volume_ratio", 0)
    price = realtime_data.get("price", 0)
    pick_price = stock.get("最新价", 0)

    if result == "成功":
        parts = []
        if today_change > 2:
            parts.append(f"涨幅较大({today_change:+.2f}%)")
        if volume_ratio > 1.5:
            parts.append(f"量比放大({volume_ratio:.1f})")
        if price > pick_price:
            price_change = (price - pick_price) / pick_price * 100
            parts.append(f"价格持续上涨({price_change:+.2f}%)")
        if not parts:
            parts.append("延续原有趋势")
        return ", ".join(parts)

    elif result == "失败":
        parts = []
        if volume_ratio < 0.8:
            parts.append(f"量比萎缩({volume_ratio:.1f})")
        if today_change < -2:
            parts.append(f"跌幅较大({today_change:+.2f}%)")
        if not parts:
            parts.append("市场轮动影响")
        return ", ".join(parts)

    return "无明显变化"


def generate_verification_report(verifications, picks_date, verify_date):
    """生成验证报告"""
    total = len(verifications)
    if total == 0:
        return "暂无验证数据"

    success_count = sum(1 for v in verifications if v["result"] == "成功")
    fail_count = sum(1 for v in verifications if v["result"] == "失败")
    avg_change = sum(v["change_pct"] for v in verifications) / total

    success_rate = success_count / total * 100 if total > 0 else 0

    # 统计各维度成功率
    dim_stats = {}
    for dim in DEFAULT_WEIGHTS:
        dim_success = sum(1 for v in verifications if dim in v["dimensions"] and v["result"] == "成功")
        dim_total = sum(1 for v in verifications if dim in v["dimensions"])
        dim_stats[dim] = {
            "success": dim_success,
            "total": dim_total,
            "rate": dim_success / dim_total if dim_total > 0 else 0
        }

    # 失败共性分析
    failed_stocks = [v for v in verifications if v["result"] == "失败"]
    common_issues = []
    if failed_stocks:
        low_volume_count = sum(1 for v in failed_stocks if "量比" in v["reason"] and "萎缩" in v["reason"])
        if low_volume_count > 0:
            common_issues.append(f"失败股票中{low_volume_count}只量比萎缩")

    # 生成报告
    lines = []
    lines.append("=" * 60)
    lines.append("选股验证报告")
    lines.append(f"验证日期: {verify_date}")
    lines.append(f"验证対象: {picks_date} 选股")
    lines.append("=" * 60)
    lines.append("")

    # 单只验证
    lines.append("【单只验证】")
    lines.append(f"{'代码':<10} {'名称':<10} {'当日涨幅':>10} {'判定':<6} {'分析原因'}")
    lines.append("-" * 60)

    for v in verifications:
        name = v.get("name", "")[:8]
        change_str = f"{v['change_pct']:+.2f}%"
        lines.append(f"{v['code']:<10} {name:<10} {change_str:>10} {v['result']:<6} {v['reason']}")

    lines.append("")

    # 汇总
    lines.append("【汇总】")
    lines.append(f"验证股票数: {total}")
    lines.append(f"成功: {success_count} ({success_rate:.1f}%)")
    lines.append(f"失败: {fail_count} ({100-success_rate:.1f}%)")
    lines.append(f"平均涨幅: {avg_change:+.2f}%")
    lines.append("")

    # 维度统计
    lines.append("【各维度成功率】")
    for dim, stats in dim_stats.items():
        rate = stats["rate"] * 100
        lines.append(f"  {dim}: {stats['success']}/{stats['total']} = {rate:.1f}%")
    lines.append("")

    # 失败共性
    if common_issues:
        lines.append("【失败共性分析】")
        for issue in common_issues:
            lines.append(f"- {issue}")
        lines.append("")

    # 优化建议
    lines.append("【优化建议】")
    suggestions = get_optimization_suggestions(dim_stats)
    for s in suggestions:
        lines.append(f"- {s}")

    lines.append("")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    return "\n".join(lines)


def get_optimization_suggestions(dim_stats):
    """生成优化建议"""
    suggestions = []

    for dim, stats in dim_stats.items():
        rate = stats["rate"]
        total = stats["total"]

        if total < 3:
            continue  # 数据不足时不建议调整

        if rate < 0.40:
            suggestions.append(f"{dim}维度成功率({rate*100:.1f}%)过低，建议降低权重或优化条件")
        elif rate > 0.70:
            suggestions.append(f"{dim}维度成功率({rate*100:.1f}%)较高，可适当提高权重")

    if not suggestions:
        suggestions.append("各维度表现正常，维持当前权重配置")

    return suggestions


def update_warfare_config(verifications):
    """更新战法权重配置"""
    config = load_warfare_config()

    # 更新维度统计
    for v in verifications:
        if v["result"] == "成功":
            for dim in v["dimensions"]:
                if dim in config["dimension_stats"]:
                    config["dimension_stats"][dim]["success"] += 1
        elif v["result"] == "失败":
            for dim in v["dimensions"]:
                if dim in config["dimension_stats"]:
                    config["dimension_stats"][dim]["fail"] += 1

    # 计算新权重
    new_weights = adjust_weights(config["weights"], config["dimension_stats"])
    config["weights"] = new_weights
    config["last_updated"] = datetime.now().strftime("%Y-%m-%d")

    save_warfare_config(config)
    return config, new_weights


def adjust_weights(current_weights, dim_stats):
    """根据维度成功率调整权重"""
    new_weights = current_weights.copy()

    for dim, stats in dim_stats.items():
        total = stats["success"] + stats["fail"]
        if total < 3:
            continue  # 数据不足时不调整

        success_rate = stats["success"] / total

        if success_rate < SUCCESS_THRESHOLD_LOW:
            # 成功率过低，减少权重
            new_weights[dim] = max(WEIGHT_MIN, new_weights[dim] - WEIGHT_ADJUSTMENT)
        elif success_rate > SUCCESS_THRESHOLD_HIGH:
            # 成功率过高，增加权重
            new_weights[dim] = min(WEIGHT_MAX, new_weights[dim] + WEIGHT_ADJUSTMENT)

    # 归一化权重
    total_weight = sum(new_weights.values())
    if abs(total_weight - 1.0) > 0.01:
        for dim in new_weights:
            new_weights[dim] = round(new_weights[dim] / total_weight, 3)

    return new_weights


def run_verification():
    """执行验证主流程"""
    logger.info("开始选股验证...")

    new_picks_detected = False

    # 自动模式下：先检查是否有新内容
    if AUTO_MODE:
        if not has_new_picks():
            logger.info("出击股票未更新，跳过验证")
            print("出击股票未更新，跳过验证")
            return
        new_picks_detected = True
        logger.info("检测到出击股票有更新，开始验证...")

    # 加载选股数据
    picks_data = load_picks()
    if not picks_data:
        logger.error("未找到选股数据文件")
        return

    # 检查选股日期（自动模式或强制模式跳过日期检查）
    picks_date = picks_data.get("最后更新", "")
    if not new_picks_detected and not FORCE_MODE:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # picks_date 可能是 "2026-04-15 15:22:05" 格式，提取日期部分比较
        picks_date_only = picks_date[:10] if len(picks_date) >= 10 else picks_date
        if picks_date_only not in [yesterday, today]:
            logger.info(f"选股日期为 {picks_date}，今日 {today}，暂无待验证数据")
            print(f"暂无待验证数据（选股日期: {picks_date}）")
            return

    # 获取出击股票
    chu_sha_stocks = picks_data.get("出击股票", [])
    if not chu_sha_stocks:
        logger.info("出击股票为空")
        print("出击股票为空")
        return

    logger.info(f"验证股票数量: {len(chu_sha_stocks)}")

    # 验证每只股票
    verifications = []
    for stock in chu_sha_stocks:
        code = stock.get("代码", "")
        logger.info(f"验证: {code}")

        # 获取实时数据
        realtime = get_realtime_data(code)

        # 评估
        result = evaluate_stock(stock, realtime, picks_date)
        verifications.append(result)

        logger.info(f"  {code}: {result['change_pct']:+.2f}% - {result['result']}")

    # 生成报告
    verify_date = datetime.now().strftime("%Y-%m-%d")
    report = generate_verification_report(verifications, picks_date, verify_date)

    # 保存报告
    with open(VER_REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)

    logger.info(f"验证报告已保存到: {VER_REPORT_FILE}")

    # 更新历史记录
    history = load_ver_history()
    history["verifications"].append({
        "date": verify_date,
        "picks_date": picks_date,
        "stocks": verifications
    })
    save_ver_history(history)

    # 打印报告
    print("\n" + report)

    return verifications


def run_feedback():
    """执行反馈优化"""
    logger.info("执行战法权重优化...")

    # 加载历史验证
    history = load_ver_history()
    all_verifications = []

    for v in history.get("verifications", []):
        all_verifications.extend(v.get("stocks", []))

    if not all_verifications:
        logger.info("暂无验证数据，无法执行优化")
        print("暂无验证数据，请先运行验证")
        return

    # 更新权重
    old_config = load_warfare_config()
    new_config, new_weights = update_warfare_config(all_verifications)

    # 打印变化
    print("\n【权重优化结果】")
    print(f"{'维度':<10} {'原权重':>10} {'新权重':>10} {'变化':>10}")
    print("-" * 40)
    for dim in DEFAULT_WEIGHTS:
        old_w = old_config["weights"].get(dim, 0)
        new_w = new_weights.get(dim, 0)
        change = new_w - old_w
        change_str = f"{change:+.3f}" if change != 0 else "—"
        print(f"{dim:<10} {old_w:>10.3f} {new_w:>10.3f} {change_str:>10}")

    print(f"\n权重配置已更新到: {WARFARE_CONFIG_FILE}")
    print(f"下次选股将使用新权重")

    return new_weights


def show_report():
    """显示最新验证报告"""
    if not VER_REPORT_FILE.exists():
        print("暂无验证报告，请先运行验证")
        return

    with open(VER_REPORT_FILE, 'r', encoding='utf-8') as f:
        print(f.read())


def show_history():
    """显示历史验证统计"""
    history = load_ver_history()
    verifications = history.get("verifications", [])

    if not verifications:
        print("暂无历史验证记录")
        return

    print(f"\n【历史验证统计】")
    print(f"验证次数: {len(verifications)}")
    print()

    # 汇总统计
    all_stocks = []
    for v in verifications:
        all_stocks.extend(v.get("stocks", []))

    total = len(all_stocks)
    success = sum(1 for s in all_stocks if s["result"] == "成功")
    fail = sum(1 for s in all_stocks if s["result"] == "失败")
    avg_change = sum(s["change_pct"] for s in all_stocks) / total if total > 0 else 0

    print(f"总验证股票数: {total}")
    print(f"成功: {success} ({success/total*100:.1f}%)" if total > 0 else "成功: 0")
    print(f"失败: {fail} ({fail/total*100:.1f}%)" if total > 0 else "失败: 0")
    print(f"平均涨幅: {avg_change:+.2f}%")
    print()

    # 最近5次验证
    print("【最近验证记录】")
    for v in verifications[-5:]:
        print(f"  {v['date']}: 验证{v['picks_date']}选股, {len(v['stocks'])}只")


def main():
    global AUTO_MODE, FORCE_MODE
    parser = argparse.ArgumentParser(description="选股验证系统")
    parser.add_argument("--feedback", action="store_true", help="执行权重优化")
    parser.add_argument("--report", action="store_true", help="显示报告")
    parser.add_argument("--history", action="store_true", help="显示历史")
    parser.add_argument("--auto", action="store_true", help="自动模式：有更新才验证")
    parser.add_argument("--force", action="store_true", help="强制验证（忽略日期检查）")

    args = parser.parse_args()
    AUTO_MODE = args.auto
    FORCE_MODE = args.force

    if args.report:
        show_report()
    elif args.history:
        show_history()
    elif args.feedback:
        run_feedback()
    else:
        run_verification()


if __name__ == "__main__":
    main()
