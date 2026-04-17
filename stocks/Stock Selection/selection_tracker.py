"""
选股跟踪记录 - 记录每周自选股和每日加仓股票
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# 延迟导入，避免循环依赖
_fetcher = None
_realtime_fetcher = None

def _get_fetcher():
    global _fetcher
    if _fetcher is None:
        from data_fetcher import get_fetcher
        _fetcher = get_fetcher()
    return _fetcher

def _get_realtime_fetcher():
    """获取实时行情获取器（用于获取股票名称，AKShare失败时的备选）"""
    global _realtime_fetcher
    if _realtime_fetcher is None:
        from realtime_fetcher import get_realtime_fetcher
        _realtime_fetcher = get_realtime_fetcher()
    return _realtime_fetcher

def _get_stock_name(code: str) -> str:
    """获取股票名称（优先AKShare，失败后用实时行情）"""
    try:
        info = _get_fetcher().get_stock_info(code)
        name = info.get("name", "") or info.get("股票名称", "")
        if name:
            return name
    except Exception:
        pass

    # 降级到实时行情
    try:
        rt_data = _get_realtime_fetcher().get_spot_single(code)
        if rt_data:
            return rt_data.get("name", "")
    except Exception:
        pass

    return ""


class SelectionTracker:
    """选股跟踪器"""

    def __init__(self, file_path: str = None):
        if file_path is None:
            base_dir = Path(__file__).parent / "View Results"
            base_dir.mkdir(exist_ok=True)
            self.tracker_file = base_dir / "出击.txt"
            self.watchlist_file = base_dir / "weekly_watchlist.txt"
        else:
            self.tracker_file = Path(file_path)
            self.watchlist_file = Path(file_path).parent / "weekly_watchlist.txt"
        self.stocks = []  # 合并后的持仓列表（持仓+新筛选）

    def _load(self) -> Dict[str, Any]:
        """加载历史记录"""
        if self.tracker_file.exists():
            try:
                with open(self.tracker_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载选股记录失败: {e}")
        return {}

    def _save(self, data: Dict[str, Any]):
        """保存记录"""
        try:
            with open(self.tracker_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存选股记录失败: {e}")

    def check_holding_signals(self, holdings: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        检查持仓股票的持有信号（李成刚核心思想：趋势持有，不频繁换股）

        拿住信号（继续持有）：
        - 缩量调整（量比<0.8），股价在10日线/20日线附近获得支撑
        - 换手率<5%，抛压枯竭
        - 股价在5日线上方，趋势向上
        - MACD绿柱持续缩短，动能转多
        - 二次探底不破新低，形成双底结构

        卖出信号（不再持有）：
        - 放量滞涨（量比>1.5但涨幅<1%）
        - 跌破10日线且3日内未能收复
        - 跌破20日线（清仓信号）
        - 涨幅>20%（追高风险）
        - 换手率突然放大至>10%（主力可能出货）
        - RSI>80（超买区域）

        Returns:
            List of dicts with code, signal, reason, pnl, etc.
        """
        if not holdings:
            return []

        fetcher = _get_fetcher()
        results = []

        for stock in holdings:
            code = stock.get("代码", "") or stock.get("code", "")
            entry_price = stock.get("持仓价", 0) or stock.get("entry_price", 0) or stock.get("最新价", 0)
            entry_date = stock.get("持仓日期", "") or stock.get("entry_date", "")

            try:
                # 获取近30日数据用于技术分析
                df = fetcher.get_daily(code, use_cache=False)
                if df is None or len(df) < 20:
                    results.append({
                        "代码": code,
                        "名称": stock.get("名称", ""),
                        "信号": "数据不足",
                        "建议": "观察",
                        "持有天数": 0,
                        "盈亏": 0,
                        "盈亏Pct": 0,
                        "理由": ["数据不足，无法判断"]
                    })
                    continue

                latest = df.iloc[-1]
                prev5 = df.iloc[-6] if len(df) >= 6 else df.iloc[0]
                prev10 = df.iloc[-11] if len(df) >= 11 else df.iloc[0]
                prev20 = df.iloc[-21] if len(df) >= 21 else df.iloc[0]

                current_price = float(latest.get("close", 0))
                prev_price = float(df.iloc[-2].get("close", 0)) if len(df) >= 2 else current_price
                vol_latest = float(latest.get("volume", 0))
                vol_ma5 = df.iloc[-5:]["volume"].mean() if len(df) >= 5 else vol_latest
                vol_ratio = vol_latest / vol_ma5 if vol_ma5 > 0 else 1.0

                # 计算均线
                ma5 = df.iloc[-5:]["close"].mean() if len(df) >= 5 else current_price
                ma10 = df.iloc[-10:]["close"].mean() if len(df) >= 10 else current_price
                ma20 = df.iloc[-20:]["close"].mean() if len(df) >= 20 else current_price

                # 计算涨跌幅
                change_pct = (current_price - prev_price) / prev_price * 100 if prev_price > 0 else 0
                entry_change_pct = (current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0

                # 持仓天数
                holding_days = 1
                if entry_date:
                    try:
                        ed = datetime.strptime(entry_date[:10], "%Y-%m-%d")
                        holding_days = max(1, (datetime.now() - ed).days)
                    except Exception:
                        holding_days = 1

                # 计算RSI
                delta = df["close"].diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, 0.001)
                rsi = (100 - (100 / (1 + rs))).iloc[-1] if len(rs) > 0 else 50

                # 计算MACD
                ema12 = df["close"].ewm(span=12, adjust=False).mean()
                ema26 = df["close"].ewm(span=26, adjust=False).mean()
                dif = (ema12 - ema26).iloc[-1]
                dea = df["close"].ewm(span=9, adjust=False).mean().iloc[-1]
                macd_hist = dif - dea

                # 换手率估算（成交量/流通股本）
                turnover = vol_latest / 1000000 if vol_latest > 0 else 0  # 简化

                # ===== 核心判断逻辑（李成刚左侧战法） =====
                signals = []
                reasons = []

                # 计算RSI历史最低
                rsi_10 = rs.iloc[-10:].min() if len(rs) >= 10 else rsi
                # 计算BOLL位置
                boll_upper = ma20 + 2 * df.iloc[-20:]["close"].std() if len(df) >= 20 else ma20 * 1.1
                boll_lower = ma20 - 2 * df.iloc[-20:]["close"].std() if len(df) >= 20 else ma20 * 0.9
                boll_pos = (current_price - boll_lower) / (boll_upper - boll_lower) * 100 if boll_upper > boll_lower else 50

                # 1. 卖出信号检查（李成刚原则）
                # 止损出局：跌破20日线 且 不是从BOLL下轨反弹的股票
                if current_price < ma20:
                    if boll_pos < 20:
                        signals.append("继续持有")
                        reasons.append(f"BOLL位置{boll_pos:.0f}%处于低位，支撑有效")
                    else:
                        signals.append("减仓观望")
                        reasons.append("跌破20日均线，等待企稳")

                # 跌破10日线：看情况
                elif current_price < ma10:
                    if boll_pos < 25 or rsi < 45:
                        signals.append("继续持有")
                        reasons.append(f"缩量回踩MA10，BOLL低位{boll_pos:.0f}%，左侧支撑强")
                    else:
                        signals.append("减仓观望")
                        reasons.append("跌破10日均线，趋势转弱")

                # 放量滞涨（李成刚：可能是主力出货）
                elif vol_ratio > 1.5 and change_pct < 1.0:
                    signals.append("分批止盈")
                    reasons.append(f"放量滞涨（量比{vol_ratio:.1f}），主力可能出货")

                # 换手率异常
                elif turnover > 10:
                    signals.append("分批止盈")
                    reasons.append(f"换手率异常放大（>{10}%），主力行为")

                # RSI超买
                elif rsi > 80:
                    signals.append("分批止盈")
                    reasons.append(f"RSI超买（{rsi:.1f}），注意锁定利润")

                # 盈利过大（>20%）
                elif entry_change_pct > 20:
                    signals.append("分批止盈")
                    reasons.append(f"持仓盈利>{20}%，锁定利润")

                # 2. 拿住信号检查（李成刚核心）
                if not signals:
                    # 强势状态：价格在所有均线上方
                    if current_price > ma5 and current_price > ma10 and current_price > ma20:
                        if vol_ratio < 0.8:
                            signals.append("继续持有")
                            reasons.append("缩量上涨，趋势健康，主力控盘")
                        else:
                            signals.append("继续持有")
                            reasons.append("趋势向上，均线多头排列")

                    # 回踩MA5但未跌破MA10（强势回踩）
                    elif current_price > ma10 and current_price < ma5:
                        if vol_ratio < 0.8:
                            signals.append("继续持有")
                            reasons.append("缩量回踩10日线，支撑有效，主力洗盘")
                        else:
                            signals.append("继续持有")
                            reasons.append("回踩10日线，量能正常，耐心持有")

                    # 在MA10-MA20之间：观察状态
                    elif current_price > ma20 and current_price < ma10:
                        if boll_pos < 20:
                            signals.append("继续持有")
                            reasons.append(f"BOLL低位{boll_pos:.0f}%，左侧买点，继续持有")
                        else:
                            signals.append("轻仓持有")
                            reasons.append("回踩20日线附近，等待方向确认")

                    # 跌破MA20但BOLL低位
                    elif current_price < ma20 and boll_pos < 25:
                        signals.append("继续持有")
                        reasons.append(f"BOLL低位{boll_pos:.0f}%，主力可能在吸筹，继续持有")

                    else:
                        signals.append("继续持有")
                        reasons.append("处于建仓成本区间，耐心等待")

                signal = signals[0] if signals else "继续持有"
                reason = reasons[0] if reasons else "无明显信号"

                results.append({
                    "代码": code,
                    "名称": stock.get("名称", ""),
                    "信号": signal,
                    "建议": signal,
                    "持有天数": holding_days,
                    "持仓价": entry_price,
                    "最新价": current_price,
                    "盈亏": current_price - entry_price,
                    "盈亏Pct": entry_change_pct,
                    "理由": reasons,
                    "技术指标": {
                        "最新价": current_price,
                        "MA5": round(ma5, 2),
                        "MA10": round(ma10, 2),
                        "MA20": round(ma20, 2),
                        "量比": round(vol_ratio, 2),
                        "换手率估算": round(turnover, 2),
                        "RSI": round(rsi, 1),
                        "MACD_DIF": round(dif, 3),
                    }
                })

            except Exception as e:
                logger.error(f"检查持仓 {code} 失败: {e}")
                results.append({
                    "代码": code,
                    "名称": stock.get("名称", ""),
                    "信号": "检查失败",
                    "建议": "观察",
                    "持有天数": 0,
                    "盈亏": 0,
                    "盈亏Pct": 0,
                    "理由": [f"检查失败: {str(e)}"]
                })

        return results

    def add_weekly_watchlist(self, stocks: List[Dict[str, Any]]):
        """记录每周自选股（同时生成出击股票）
        李成刚核心改进：保留已有持仓股票，不频繁换股
        """
        data = self._load()
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data["最后更新"] = today
        data["本周自选股"] = []
        data["加仓股票"] = []
        data["出击股票"] = []  # 从加仓股票中精选的前5只
        data["出击分级"] = {"主攻": [], "次攻": [], "观察": []}  # 新增分级

        # 李成刚：保存大盘趋势
        if stocks:
            data["大盘趋势"] = stocks[0].get("大盘趋势", "未知") if stocks else "未知"
            data["建议仓位"] = stocks[0].get("建议仓位", "未知") if stocks else "未知"

        buy_signals = ["加仓", "买入", "强烈推荐", "左侧买入"]

        # ====== Step 1: 检查已有持仓是否该继续持有 ======
        existing_positions = data.get("持仓记录", [])
        held_stocks = []  # 保留到出击列表的持仓股票
        position_updates = {}  # code -> updated position data

        if existing_positions:
            holding_results = self.check_holding_signals(existing_positions)
            for result in holding_results:
                code = result.get("代码", "")
                signal = result.get("信号", "继续持有")
                # 只要不是"止损出局"或"检查失败"，就保留持仓
                if signal not in ["止损出局", "检查失败"]:
                    # 找原持仓数据
                    orig = next((p for p in existing_positions if p.get("代码") == code), {})
                    # 获取技术指标
                    tech_indicators = result.get("技术指标", {})
                    held_stocks.append({
                        "代码": code,
                        "名称": result.get("名称", orig.get("名称", "")),
                        "评级": orig.get("评级", "B"),
                        # 使用check_holding_signals的原始结果，不重新生成
                        "信号": result.get("信号", f"持仓{result.get('持有天数', 0)}天-{signal}"),
                        "评分": orig.get("评分", 70),  # 持仓股票给个保底评分
                        "持仓价": result.get("持仓价", 0),
                        "最新价": result.get("最新价", orig.get("持仓价", 0)),
                        "涨跌幅": result.get("盈亏Pct", 0),
                        "持有天数": result.get("持有天数", 0),
                        "止损": orig.get("止损位", ""),
                        "止盈": orig.get("止盈位", ""),
                        "理由": result.get("理由", []),
                        "分级": orig.get("分级", "次攻"),
                        "仓位建议": orig.get("仓位建议", "正常仓位"),
                        "启动信号": False,
                        "启动强度": "",
                        "明日买入条件": orig.get("明日买入条件", {}),
                        "技术指标": tech_indicators,  # 顶层，供get_holding_report使用
                        "持仓信息": {
                            "持仓价": result.get("持仓价", 0),
                            "最新价": result.get("最新价", 0),
                            "盈亏": result.get("盈亏", 0),
                            "盈亏Pct": result.get("盈亏Pct", 0),
                            "持有天数": result.get("持有天数", 0),
                            "持有信号": signal,
                            "技术指标": tech_indicators,
                        }
                    })
                # 更新持仓记录中的最新价格和盈亏
                for pos in data.get("持仓记录", []):
                    if pos.get("代码") == code:
                        pos["当前价"] = result.get("最新价", pos.get("持仓价", 0))
                        pos["盈亏"] = result.get("盈亏", 0)
                        pos["盈亏Pct"] = result.get("盈亏Pct", 0)
                        pos["持仓天数"] = result.get("持有天数", 0)
                        pos["持有信号"] = signal
                        break

        # ====== Step 2: 处理新选出的股票 ======
        new_codes = set()
        for stock in stocks:
            # 支持中英文键名
            code = stock.get("code", "") or stock.get("代码", "")
            new_codes.add(code)

            # 获取股票名称
            name = stock.get("name", "") or stock.get("名称", "")
            if not name:
                name = _get_stock_name(code)

            stock_info = {
                "代码": code,
                "名称": name,
                "评级": stock.get("评级", "B"),
                "信号": stock.get("信号", ""),
                "评分": stock.get("总分", 0) or stock.get("评分", 0),
                "最新价": stock.get("最新价", 0) or stock.get("current", 0) or stock.get("price", 0),
                "涨跌幅": stock.get("涨跌幅", 0) or stock.get("pct_chg", 0) or stock.get("change_pct", 0),
                "止损": stock.get("止损", ""),
                "止盈": stock.get("止盈", ""),
                "理由": stock.get("理由", []),
                "分级": stock.get("分级", ""),
                "仓位建议": stock.get("仓位建议", ""),
                "启动信号": stock.get("启动信号", False),
                "启动强度": stock.get("启动强度", ""),
                "明日买入条件": stock.get("明日买入条件", {}),
            }
            data["本周自选股"].append(stock_info)

            # 同时记录加仓股票（支持包含匹配，如"左侧买入（明日观察）"匹配"左侧买入"）
            if any(bs in stock.get("信号", "") for bs in buy_signals):
                data["加仓股票"].append(stock_info)

        # ====== Step 3: 合并持仓股票（新股票不重复） ======
        for hs in held_stocks:
            if hs["代码"] not in new_codes:
                data["本周自选股"].append(hs)
                data["加仓股票"].append(hs)

        # 保存合并后的自选股列表供save_weekly_watchlist使用
        self.stocks = data["本周自选股"]

        # ====== Step 4: 精选出击股票 ======
        # 从加仓股票中精选出击股票：评分>=68且价格<80元，且涨幅<=15%（李成刚：涨停不追）
        buyable = [s for s in data["加仓股票"]
                   if s["评分"] >= 65  # 持仓股票保底65分，新股>=68
                   and s["最新价"] < 80
                   and abs(s.get("涨跌幅", 0)) <= 15]  # 李成刚：排除大涨大跌
        buyable.sort(key=lambda x: x["评分"], reverse=True)
        data["出击股票"] = buyable[:8]  # 扩大上限到8只，留空间给持仓股

        # 分级整理：主攻2只 + 次攻 + 观察
        main_attack = [s for s in buyable if s.get("分级") == "主攻"][:2]
        secondary = [s for s in buyable if s.get("分级") == "次攻"][:4]  # 次攻扩大
        observe = [s for s in buyable if s.get("分级") == "观察"][:2]  # 观察扩大

        data["出击分级"] = {
            "主攻": main_attack,
            "次攻": secondary,
            "观察": observe,
        }

        # ====== Step 5: 记录持仓检查结果 ======
        data["持仓检查"] = {
            "时间": today,
            "持仓数": len(existing_positions),
            "继续持有": len([h for h in held_stocks if "继续持有" in h.get("信号", "")]),
            "建议卖出": len([h for h in held_stocks if h.get("信号", "") in ["止损出局", "分批止盈", "减仓观望"]]),
            "详情": held_stocks,
        }

        self._save(data)
        logger.info(f"已记录本周自选股 {len(stocks)} 只，其中出击 {len(data['出击股票'])} 只")
        logger.info(f"持仓保留：{len(held_stocks)} 只，分级：主攻{len(main_attack)}只，次攻{len(secondary)}只，观察{len(observe)}只")

    def add_buy_signal(self, stocks: List[Dict[str, Any]]):
        """记录每日加仓股票"""
        data = self._load()
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "每日加仓记录" not in data:
            data["每日加仓记录"] = []

        # 添加新的加仓记录
        for stock in stocks:
            code = stock.get("code", "") or stock.get("代码", "")
            name = stock.get("name", "") or stock.get("名称", "")
            buy_info = {
                "日期": today,
                "代码": code,
                "名称": name,
                "信号": stock.get("信号", ""),
                "评分": stock.get("总分", 0) or stock.get("评分", 0),
                "止损位": stock.get("止损", ""),
                "止盈位": stock.get("止盈", ""),
                "理由": stock.get("理由", []),
                "最新价": stock.get("最新价", 0) or stock.get("current", 0),
            }
            data["每日加仓记录"].append(buy_info)

        self._save(data)
        logger.info(f"已记录今日加仓股票 {len(stocks)} 只")

    def add_position(self, code: str, name: str, entry_price: float, stop_loss: float,
                     take_profit: float, reason: str, entry_date: str = None,
                     rating: str = "B", score: float = 70, grade: str = "次攻",
                     position_note: str = "正常仓位", tomorrow_conditions: Dict = None):
        """添加或更新持仓信息"""
        data = self._load()
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "持仓记录" not in data:
            data["持仓记录"] = []

        # 检查是否已存在
        found = False
        for pos in data["持仓记录"]:
            if pos["代码"] == code:
                pos["持仓日期"] = entry_date or today
                pos["持仓价"] = entry_price
                pos["当前价"] = entry_price
                pos["止损位"] = stop_loss
                pos["止盈位"] = take_profit
                pos["持仓理由"] = reason
                pos["状态"] = "持仓中"
                pos["评级"] = rating
                pos["评分"] = score
                pos["分级"] = grade
                pos["仓位建议"] = position_note
                if name:
                    pos["名称"] = name
                if tomorrow_conditions:
                    pos["明日买入条件"] = tomorrow_conditions
                found = True
                break

        if not found:
            data["持仓记录"].append({
                "代码": code,
                "名称": name,
                "持仓日期": entry_date or today,
                "持仓价": entry_price,
                "当前价": entry_price,
                "止损位": stop_loss,
                "止盈位": take_profit,
                "持仓理由": reason,
                "状态": "持仓中",
                "评级": rating,
                "评分": score,
                "分级": grade,
                "仓位建议": position_note,
                "盈亏": 0,
                "盈亏Pct": 0,
                "持仓天数": 0,
                "持有信号": "",
                "明日买入条件": tomorrow_conditions or {},
            })

        self._save(data)
        logger.info(f"已添加/更新持仓记录: {code} {name}")

    def update_position(self, code: str, entry_price: float, stop_loss: float,
                       take_profit: float, reason: str):
        """更新持仓信息（兼容旧接口）"""
        self.add_position(code, "", entry_price, stop_loss, take_profit, reason)

    def get_holding_report(self) -> str:
        """生成持仓检查报告（李成刚：波段持有，趋势操作）"""
        data = self._load()
        holdings = data.get("持仓记录", [])
        if not holdings:
            return "暂无持仓记录"

        # 使用add_weekly_watchlist中已存储的检查结果，避免重复计算导致不一致
        holding_results = data.get("持仓检查", {}).get("详情", None)
        if not holding_results:
            # 如果没有存储的详情，才重新计算（兼容旧数据）
            holding_results = self.check_holding_signals(holdings)

        lines = []
        lines.append("=" * 60)
        lines.append("【持仓检查报告】")
        lines.append(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)

        # 汇总
        hold_count = sum(1 for r in holding_results if "继续持有" in r.get("信号", ""))
        sell_count = sum(1 for r in holding_results if r.get("信号", "") in ["止损出局", "分批止盈", "减仓观望", "观望等待"])

        lines.append(f"\n持仓总数: {len(holdings)}")
        lines.append(f"  继续持有: {hold_count} 只")
        lines.append(f"  建议操作: {sell_count} 只")

        # 详细
        lines.append("")
        lines.append("【持仓明细】")
        lines.append(f"{'代码':<10} {'名称':<10} {'信号':<12} {'持仓价':>8} {'现价':>8} {'盈亏%':>8} {'天数':>5} 核心理由")
        lines.append("-" * 75)

        for r in holding_results:
            code = r.get("代码", "")
            name = r.get("名称", "")[:8]
            signal = r.get("信号", "")[:10]
            entry_p = r.get("持仓价", 0)
            curr_p = r.get("最新价", 0)
            pnl = r.get("盈亏Pct", 0)
            days = r.get("持有天数", 0)
            reason = r.get("理由", [""])[0][:15]

            entry_s = f"{entry_p:.2f}" if entry_p else "-"
            curr_s = f"{curr_p:.2f}" if curr_p else "-"
            pnl_s = f"{pnl:+.1f}%" if pnl else "-"

            lines.append(f"{code:<10} {name:<10} {signal:<12} {entry_s:>8} {curr_s:>8} {pnl_s:>8} {days:>5}  {reason}")

        # 技术指标
        lines.append("")
        lines.append("【技术指标】")
        lines.append(f"{'代码':<10} {'名称':<10} {'MA5':>8} {'MA10':>8} {'MA20':>8} {'量比':>6} {'RSI':>6} {'信号'}")
        lines.append("-" * 70)

        for r in holding_results:
            ti = r.get("技术指标", {})
            code = r.get("代码", "")
            name = r.get("名称", "")[:8]
            ma5 = ti.get("MA5", 0)
            ma10 = ti.get("MA10", 0)
            ma20 = ti.get("MA20", 0)
            vol_r = ti.get("量比", 0)
            rsi = ti.get("RSI", 0)
            signal = r.get("信号", "")[:6]

            lines.append(f"{code:<10} {name:<10} {ma5:>8.2f} {ma10:>8.2f} {ma20:>8.2f} {vol_r:>6.2f} {rsi:>6.1f} {signal}")

        lines.append("")
        return "\n".join(lines)

    def get_watchlist(self) -> List[Dict[str, Any]]:
        """获取本周自选股"""
        data = self._load()
        return data.get("本周自选股", [])

    def get_buy_signals(self) -> List[Dict[str, Any]]:
        """获取今日加仓股票"""
        data = self._load()
        return data.get("每日加仓记录", [])

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓记录"""
        data = self._load()
        return data.get("持仓记录", [])

    def generate_report(self) -> str:
        """生成选股报告（可读格式）"""
        data = self._load()
        lines = []

        # 股票代码到名称的映射
        STOCK_NAMES = {
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

        # 出击股票（竖向排版）
        出击 = data.get("出击股票", [])
        出击分级 = data.get("出击分级", {})

        # 大盘趋势
        market_trend = data.get("大盘趋势", "未知")
        position_limit = data.get("建议仓位", "未知")

        if 出击:
            lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")
            # 李成刚核心：加入大盘趋势
            lines.append("【大盘趋势参考】")
            lines.append(f"  当前趋势: {market_trend}")
            lines.append(f"  建议仓位: {position_limit}")
            lines.append(f"  核心原则: 顺势而为，大盘下跌时多看少动")
            lines.append("")
            lines.append(f"今日可出击股票共有 {len(出击)} 只")
            lines.append("")

            # 分级显示
            if 出击分级:
                # 主攻
                主攻 = 出击分级.get("主攻", [])
                if 主攻:
                    lines.append("【主攻】- 重仓出击，主升浪起涨点")
                    for i, s in enumerate(主攻, 1):
                        lines.extend(self._format_stock_entry(s, f"主攻{i}"))
                    lines.append("")

                # 次攻
                次攻 = 出击分级.get("次攻", [])
                if 次攻:
                    lines.append("【次攻】- 正常仓位，顺势而为")
                    for i, s in enumerate(次攻, 1):
                        lines.extend(self._format_stock_entry(s, f"次攻{i}"))
                    lines.append("")

                # 观察
                观察 = 出击分级.get("观察", [])
                if 观察:
                    lines.append("【观察】- 轻仓观察，等待确认")
                    for i, s in enumerate(观察, 1):
                        lines.extend(self._format_stock_entry(s, f"观察{i}"))
                    lines.append("")

            # 其他出击股票（不在分级中的）
            graded_codes = set(s.get('代码') for s in 主攻 + 次攻 + 观察)
            other_attack = [s for s in 出击 if s.get('代码') not in graded_codes]
            if other_attack:
                lines.append("【其他出击】")
                for i, s in enumerate(other_attack, 1):
                    lines.extend(self._format_stock_entry(s, f"{i}"))
                lines.append("")

        lines.append("")
        return "\n".join(lines)

    def _format_stock_entry(self, s: Dict[str, Any], index: str) -> List[str]:
        """格式化单个股票条目"""
        STOCK_NAMES = {
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
            # 6.2新增股票名称
            "002235": "安妮股份", "300901": "中胤时尚",
            "301256": "华融化学", "002081": "金螳螂",
            "002771": "真视通", "301012": "扬电科技",
            "601619": "嘉泽新能", "001300": "三柏硕",
            "300352": "北信源", "601388": "怡球资源",
            "300845": "捷安高科", "600590": "泰豪科技",
        }

        lines = []
        code = s.get('代码', s.get('code', ''))
        name = s.get('名称', s.get('name', STOCK_NAMES.get(code, '')))
        if not name:
            name = STOCK_NAMES.get(code, '')
        rating = s.get('评级', s.get('rating', ''))
        score = s.get('评分', s.get('总分', s.get('score', 0)))
        # 持仓股票的信号优先用持仓检查结果（避免重复计算导致不一致）
        signal = s.get('信号', s.get('signal', ''))
        pos_info = s.get('持仓信息', {})
        if pos_info:
            stored_signal = pos_info.get('持有信号', '')
            if stored_signal:
                signal = f"持仓{pos_info.get('持有天数', 0)}天-{stored_signal}"
        # 最佳买入区间 = 最新价上下1%
        price = s.get('最新价', s.get('price', 0))
        buy_range = f"{price*0.99:.2f}-{price*1.01:.2f}" if price else ""
        take_profit = s.get('止盈', s.get('止盈位', s.get('take_profit', '')))
        stop_loss = s.get('止损', s.get('止损位', s.get('stop_loss', '')))
        # 新增字段
        grade = s.get('分级', '')
        position_note = s.get('仓位建议', '')
        breakout = s.get('启动信号', False)
        breakout_strength = s.get('启动强度', '')

        reasons = s.get('理由', s.get('reasons', []))
        reason_str = '，'.join(reasons) if isinstance(reasons, list) else str(reasons)

        # 明日买入条件（李成刚核心）
        tomorrow = s.get('明日买入条件', {})
        buy_zone = tomorrow.get('买入区间', buy_range) if tomorrow else buy_range
        triggers = tomorrow.get('触发条件', []) if tomorrow else []
        observations = tomorrow.get('观察要点', []) if tomorrow else []
        no_buy = tomorrow.get('不买条件', []) if tomorrow else []
        risk = tomorrow.get('风险提示', '') if tomorrow else ''

        lines.append(f"【{index}】{code} {name}")
        lines.append(f"    评级: {rating}")
        lines.append(f"    评分: {score:.1f}")
        lines.append(f"    分级: {grade}")
        lines.append(f"    信号: {signal}")
        lines.append(f"    最新价: {price:.2f}")
        lines.append(f"    仓位建议: {position_note}")
        if breakout:
            lines.append(f"    启动信号: {breakout_strength}")

        # 李成刚：明日买入条件
        lines.append("")
        lines.append(f"  ★ 明日买入区间: {buy_zone}")
        if triggers:
            lines.append(f"  ★ 触发条件:")
            for t in triggers:
                lines.append(f"      - {t}")
        if observations:
            lines.append(f"  ★ 观察要点:")
            for o in observations:
                lines.append(f"      - {o}")
        if no_buy:
            lines.append(f"  ★ 不买条件:")
            for n in no_buy:
                lines.append(f"      - {n}")
        if risk:
            lines.append(f"  ⚠ 风险提示: {risk}")

        lines.append(f"  今日理由: {reason_str}")
        lines.append(f"    止盈位: {take_profit}")
        lines.append(f"    止损位: {stop_loss}")
        lines.append("")
        return lines

    def save_report(self):
        """保存报告到文件"""
        report = self.generate_report()
        report_file = self.tracker_file.parent / "出击.报告.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"报告已保存到: {report_file}")

    def save_weekly_watchlist(self, stocks: List[Dict[str, Any]] = None):
        """保存自选股池到weekly_watchlist.txt（代码+名称，用于备份复盘）

        Args:
            stocks: 忽略此参数，始终保存self.stocks（合并后的持仓列表）
        """
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 使用合并后的持仓列表
        stocks_to_save = self.stocks if self.stocks else (stocks or [])

        # 股票代码到名称的映射
        STOCK_NAMES = {
            "000001": "平安银行", "600016": "民生银行", "600036": "招商银行",
            "601166": "兴业银行", "601288": "农业银行", "601328": "交通银行",
            "601398": "工商银行", "601818": "光大银行", "600000": "浦发银行",
            "600030": "中信证券", "600837": "海通证券", "601066": "中信建投",
            "601211": "国泰君安", "601688": "华泰证券", "000776": "广发证券",
            "601318": "中国平安", "601601": "新华保险", "601628": "中国人寿",
            "000568": "泸州老窖", "000858": "五粮液", "600519": "贵州茅台",
            "603288": "海天味业", "000799": "酒鬼酒", "002304": "洋河股份",
            "600809": "山西汾酒", "000596": "古井贡酒",
            "002235": "安妮股份", "300901": "中一科技",
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
            "600760": "中航沈飞", "002557": "恰恰食品", "601012": "隆基绿能",
            "600032": "三花智控", "002459": "晶澳科技", "300014": "亿纬锂能",
            "600109": "国金证券", "601555": "东吴证券", "000712": "锦龙股份",
            "601878": "浙商证券", "601336": "新华保险", "601319": "中国人保",
            "000799": "酒鬼酒", "002304": "洋河股份", "000596": "古井贡酒",
        }

        lines = []
        lines.append("=" * 60)
        lines.append(f"自选股池 - 更新日期: {today}")
        lines.append("=" * 60)
        lines.append(f"共 {len(stocks_to_save)} 只股票\n")

        # 保留代码和名称
        for stock in stocks_to_save:
            code = stock.get('code', '') or stock.get('代码', '')
            name = stock.get('name', '') or stock.get('名称', '') or STOCK_NAMES.get(code, '')
            lines.append(f"{code} - {name}")

        with open(self.watchlist_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        logger.info(f"自选股池已保存到: {self.watchlist_file}")


# 单例
_tracker_instance = None

def get_tracker() -> SelectionTracker:
    """获取跟踪器单例"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = SelectionTracker()
    return _tracker_instance