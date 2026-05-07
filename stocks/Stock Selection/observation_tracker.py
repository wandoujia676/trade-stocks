"""
观察池跟踪器 - 小金库 9.0 右侧确认机制
核心逻辑：左侧信号触发 → 入观察池 → T+1~T+3 确认（实体阳+量比>1.5）→ 晋级出击池
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 延迟导入，避免循环依赖
_fetcher = None
_selection_tracker = None

def _get_fetcher():
    global _fetcher
    if _fetcher is None:
        from data_fetcher import get_fetcher
        _fetcher = get_fetcher()
    return _fetcher

def _get_selection_tracker():
    global _selection_tracker
    if _selection_tracker is None:
        from selection_tracker import SelectionTracker
        _selection_tracker = SelectionTracker()
    return _selection_tracker


class ObservationTracker:
    """观察池跟踪器"""

    def __init__(self, file_path: str = None):
        if file_path is None:
            base_dir = Path(__file__).parent / "View Results"
            base_dir.mkdir(exist_ok=True)
            self.pool_file = base_dir / "观察池.json"
        else:
            self.pool_file = Path(file_path)

    def _load(self) -> Dict[str, Any]:
        """加载观察池数据"""
        if self.pool_file.exists():
            try:
                with open(self.pool_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载观察池失败: {e}")
        return {"最后更新": "", "观察池": []}

    def _save(self, data: Dict[str, Any]):
        """保存观察池数据"""
        try:
            data["最后更新"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.pool_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存观察池失败: {e}")

    def _get_next_trade_dates(self, start_date: str, count: int = 3) -> List[str]:
        """
        获取接下来的N个交易日
        start_date: YYYY-MM-DD 格式
        count: 需要的交易日数量
        返回: ["YYYY-MM-DD", ...] 格式的日期列表
        """
        try:
            fetcher = _get_fetcher()
            # 获取未来30天的日期范围（足够覆盖3个交易日+周末节假日）
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = start + timedelta(days=30)

            # 尝试获取一段历史数据来推断交易日（用任意股票如000001）
            df = fetcher.get_daily("000001",
                                   start_date=start.strftime("%Y%m%d"),
                                   end_date=end.strftime("%Y%m%d"))

            if df is not None and not df.empty:
                # 提取交易日期
                if 'trade_date' in df.columns:
                    dates = df['trade_date'].astype(str).tolist()
                elif 'date' in df.columns:
                    dates = df['date'].astype(str).tolist()
                else:
                    dates = df.index.astype(str).tolist()

                # 转换为 YYYY-MM-DD 格式
                trade_dates = []
                for d in dates:
                    if len(d) == 8:  # YYYYMMDD
                        trade_dates.append(f"{d[:4]}-{d[4:6]}-{d[6:]}")
                    elif len(d) == 10 and '-' in d:  # YYYY-MM-DD
                        trade_dates.append(d)

                # 过滤出 start_date 之后的日期
                future_dates = [d for d in trade_dates if d > start_date]
                return future_dates[:count]

        except Exception as e:
            logger.warning(f"获取交易日历失败: {e}，使用简单日期推算")

        # 降级方案：简单跳过周末
        result = []
        current = start + timedelta(days=1)
        while len(result) < count:
            # 跳过周六(5)和周日(6)
            if current.weekday() < 5:
                result.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return result

    def add(self, stock_code: str, stock_name: str, entry_signal: str,
            entry_price: float, entry_score: float, entry_date: str = None) -> bool:
        """
        添加股票到观察池

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            entry_signal: 入池信号（如"RSI<25 + BOLL下轨<15%"）
            entry_price: 入池价格
            entry_score: 入池评分
            entry_date: 入池日期（YYYY-MM-DD），默认今天

        Returns:
            是否添加成功
        """
        if not entry_date:
            entry_date = datetime.now().strftime("%Y-%m-%d")

        data = self._load()

        # 检查是否已存在
        for stock in data["观察池"]:
            if stock["代码"] == stock_code and stock["状态"] == "pending":
                logger.info(f"{stock_code} 已在观察池中，跳过")
                return False

        # 计算确认窗口（T+1, T+2, T+3）
        confirm_window = self._get_next_trade_dates(entry_date, count=3)

        # 添加新记录
        new_entry = {
            "代码": stock_code,
            "名称": stock_name,
            "入池日期": entry_date,
            "入池价": entry_price,
            "入池信号": entry_signal,
            "入池评分": entry_score,
            "状态": "pending",
            "确认窗口": confirm_window,
            "确认结果": None
        }

        data["观察池"].append(new_entry)
        self._save(data)
        logger.info(f"✅ {stock_code} {stock_name} 已加入观察池，确认窗口: {confirm_window}")
        return True

    def check_confirmation(self, stock_code: str, check_date: str = None) -> Optional[Dict[str, Any]]:
        """
        检查单只股票的右侧确认

        Args:
            stock_code: 股票代码
            check_date: 检查日期（YYYY-MM-DD），默认今天

        Returns:
            确认结果字典，包含 confirmed(bool), reason(str), details(dict)
        """
        if not check_date:
            check_date = datetime.now().strftime("%Y-%m-%d")

        try:
            fetcher = _get_fetcher()

            # 获取最近5天数据（用于计算5日均量）
            end_date = datetime.strptime(check_date, "%Y-%m-%d")
            start_date = end_date - timedelta(days=10)

            df = fetcher.get_daily(
                stock_code,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d")
            )

            if df is None or df.empty or len(df) < 2:
                return {
                    "confirmed": False,
                    "reason": "数据不足",
                    "details": {}
                }

            # 获取最新一天的数据
            latest = df.iloc[-1]
            open_price = float(latest.get('open', 0))
            close_price = float(latest.get('close', 0))
            volume = float(latest.get('volume', 0))

            # 计算5日均量
            if len(df) >= 5:
                vol_5avg = df['volume'].iloc[-6:-1].mean()  # 前5天均量（不含今天）
            else:
                vol_5avg = df['volume'].iloc[:-1].mean()

            # 计算量比
            vol_ratio = volume / vol_5avg if vol_5avg > 0 else 1.0

            # 判断实体阳线
            is_bullish = close_price > open_price
            body_pct = (close_price - open_price) / open_price * 100 if open_price > 0 else 0

            # 右侧确认规则：实体阳（收盘>开盘）+ 量比>1.5
            confirmed = is_bullish and vol_ratio > 1.5

            details = {
                "开盘价": round(open_price, 2),
                "收盘价": round(close_price, 2),
                "实体涨幅": round(body_pct, 2),
                "成交量": int(volume),
                "5日均量": int(vol_5avg),
                "量比": round(vol_ratio, 2),
                "是否收阳": is_bullish,
                "量比达标": vol_ratio > 1.5
            }

            if confirmed:
                reason = f"✅ 右侧确认：实体阳+{body_pct:.1f}% + 量比{vol_ratio:.1f}"
            elif not is_bullish:
                reason = f"❌ 未收阳线（实体{body_pct:.1f}%）"
            else:
                reason = f"❌ 量比不足（{vol_ratio:.1f} < 1.5）"

            return {
                "confirmed": confirmed,
                "reason": reason,
                "details": details
            }

        except Exception as e:
            logger.error(f"检查 {stock_code} 确认失败: {e}")
            return {
                "confirmed": False,
                "reason": f"检查失败: {str(e)}",
                "details": {}
            }

    def check_all(self, check_date: str = None) -> Dict[str, Any]:
        """
        检查所有 pending 状态的股票

        Args:
            check_date: 检查日期（YYYY-MM-DD），默认今天

        Returns:
            统计结果 {"confirmed": [...], "rejected": [...], "pending": [...]}
        """
        if not check_date:
            check_date = datetime.now().strftime("%Y-%m-%d")

        data = self._load()
        result = {
            "confirmed": [],
            "rejected": [],
            "pending": []
        }

        for stock in data["观察池"]:
            if stock["状态"] != "pending":
                continue

            code = stock["代码"]
            confirm_window = stock.get("确认窗口", [])

            # 检查是否在确认窗口内
            if check_date not in confirm_window:
                # 检查是否已过期（超过最后一个窗口日期）
                if confirm_window and check_date > confirm_window[-1]:
                    stock["状态"] = "rejected"
                    stock["确认结果"] = {
                        "confirmed": False,
                        "reason": f"超过确认窗口（{confirm_window[-1]}）未确认",
                        "details": {}
                    }
                    result["rejected"].append(stock)
                    logger.info(f"❌ {code} {stock['名称']} 已过期退池")
                else:
                    result["pending"].append(stock)
                continue

            # 执行确认检查
            confirm_result = self.check_confirmation(code, check_date)

            if confirm_result["confirmed"]:
                # 确认通过 → 晋级出击池
                stock["状态"] = "confirmed"
                stock["确认结果"] = confirm_result
                result["confirmed"].append(stock)
                logger.info(f"✅ {code} {stock['名称']} 右侧确认通过")

                # TODO: 调用 selection_tracker 写入出击池（需要完整的股票数据）
                # self._promote_to_attack(stock)

            elif check_date == confirm_window[-1]:
                # 最后一天仍未确认 → 退池
                stock["状态"] = "rejected"
                stock["确认结果"] = confirm_result
                result["rejected"].append(stock)
                logger.info(f"❌ {code} {stock['名称']} 确认窗口结束，退池")

            else:
                # 继续等待
                result["pending"].append(stock)
                logger.info(f"⏳ {code} {stock['名称']} 等待确认: {confirm_result['reason']}")

        self._save(data)
        return result

    def list_by_status(self, status: str = None) -> List[Dict[str, Any]]:
        """
        列出观察池股票

        Args:
            status: 状态筛选 ("pending", "confirmed", "rejected")，None 表示全部

        Returns:
            股票列表
        """
        data = self._load()
        stocks = data.get("观察池", [])

        if status:
            stocks = [s for s in stocks if s.get("状态") == status]

        return stocks

    def remove(self, stock_code: str) -> bool:
        """
        手动移出观察池

        Args:
            stock_code: 股票代码

        Returns:
            是否移除成功
        """
        data = self._load()
        original_count = len(data["观察池"])

        data["观察池"] = [s for s in data["观察池"]
                          if not (s["代码"] == stock_code and s["状态"] == "pending")]

        if len(data["观察池"]) < original_count:
            self._save(data)
            logger.info(f"✅ {stock_code} 已从观察池移除")
            return True

        logger.warning(f"❌ {stock_code} 不在观察池中")
        return False

    def expire_old(self, today: str = None) -> int:
        """
        清理过期记录（超过确认窗口仍未确认的）

        Args:
            today: 当前日期（YYYY-MM-DD），默认今天

        Returns:
            清理数量
        """
        if not today:
            today = datetime.now().strftime("%Y-%m-%d")

        data = self._load()
        expired_count = 0

        for stock in data["观察池"]:
            if stock["状态"] == "pending":
                confirm_window = stock.get("确认窗口", [])
                if confirm_window and today > confirm_window[-1]:
                    stock["状态"] = "rejected"
                    stock["确认结果"] = {
                        "confirmed": False,
                        "reason": f"超过确认窗口（{confirm_window[-1]}）",
                        "details": {}
                    }
                    expired_count += 1

        if expired_count > 0:
            self._save(data)
            logger.info(f"✅ 清理 {expired_count} 条过期记录")

        return expired_count


def get_observation_tracker(file_path: str = None) -> ObservationTracker:
    """获取观察池跟踪器实例"""
    return ObservationTracker(file_path)
