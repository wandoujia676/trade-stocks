"""
股票监控系统
监控自选股，检测交易信号，生成提醒
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import MONITOR_DEFAULTS, MONITOR_FILE, ALERTS_FILE
from data_fetcher import get_fetcher
from analyzer import get_analyzer

logger = logging.getLogger(__name__)


class WatchlistManager:
    """自选股管理器"""

    def __init__(self, watchlist_file: Path = MONITOR_FILE):
        self.watchlist_file = Path(watchlist_file)
        self._ensure_file()

    def _ensure_file(self):
        if not self.watchlist_file.exists():
            self._save([])

    def _load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.watchlist_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载自选股失败: {e}")
            return []

    def _save(self, watchlist: List[Dict[str, Any]]):
        try:
            with open(self.watchlist_file, 'w', encoding='utf-8') as f:
                json.dump(watchlist, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存自选股失败: {e}")

    def add(self, code: str, note: str = "") -> bool:
        """添加股票到自选"""
        watchlist = self._load()

        # 检查是否已存在
        if any(w['code'] == code for w in watchlist):
            logger.info(f"{code} 已在自选列表中")
            return False

        watchlist.append({
            "code": code.strip(),
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "note": note,
            "buy_price": None,  # 买入价
            "target_price": None,  # 目标价
            "stop_loss": None,  # 止损价
        })

        self._save(watchlist)
        logger.info(f"已添加 {code} 到自选列表")
        return True

    def remove(self, code: str) -> bool:
        """从自选移除股票"""
        watchlist = self._load()
        original_len = len(watchlist)
        watchlist = [w for w in watchlist if w['code'] != code]

        if len(watchlist) < original_len:
            self._save(watchlist)
            logger.info(f"已从自选列表移除 {code}")
            return True
        return False

    def list(self) -> List[Dict[str, Any]]:
        """列出所有自选股"""
        return self._load()

    def update_price(self, code: str, current_price: float):
        """更新持仓价格信息"""
        watchlist = self._load()
        for w in watchlist:
            if w['code'] == code:
                w['current_price'] = current_price
                w['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                self._save(watchlist)
                return True
        return False


class AlertManager:
    """提醒管理器"""

    def __init__(self, alerts_file: Path = ALERTS_FILE):
        self.alerts_file = Path(alerts_file)
        self._ensure_file()

    def _ensure_file(self):
        if not self.alerts_file.exists():
            self._save([])

    def _load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.alerts_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, alerts: List[Dict[str, Any]]):
        try:
            with open(self.alerts_file, 'w', encoding='utf-8') as f:
                json.dump(alerts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存提醒失败: {e}")

    def add_alert(self, alert: Dict[str, Any]) -> bool:
        """添加新提醒"""
        alerts = self._load()

        # 检查是否重复（相同代码+相同类型+较短时间内的）
        recent_alerts = [
            a for a in alerts
            if a.get("code") == alert.get("code")
            and a.get("type") == alert.get("type")
            and self._is_recent(a.get("time", ""))
        ]

        if recent_alerts:
            logger.debug(f"近期已有相似提醒，跳过: {alert}")
            return False

        alerts.insert(0, {
            **alert,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "read": False
        })

        # 只保留最近100条
        alerts = alerts[:100]
        self._save(alerts)
        return True

    def _is_recent(self, time_str: str) -> bool:
        """判断提醒是否在近期（30分钟内）"""
        try:
            alert_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            diff = (datetime.now() - alert_time).total_seconds()
            return diff < 1800  # 30分钟
        except:
            return False

    def get_unread(self) -> List[Dict[str, Any]]:
        """获取未读提醒"""
        alerts = self._load()
        return [a for a in alerts if not a.get("read", False)]

    def mark_read(self, alert_time: str):
        """标记提醒为已读"""
        alerts = self._load()
        for a in alerts:
            if a.get("time") == alert_time:
                a["read"] = True
                self._save(alerts)
                return True
        return False

    def mark_all_read(self):
        """标记所有提醒为已读"""
        alerts = self._load()
        for a in alerts:
            a["read"] = True
        self._save(alerts)


class StockMonitor:
    """
    股票监控器
    检查自选股的交易信号
    """

    def __init__(self, params: Dict[str, Any] = None):
        self.params = {**MONITOR_DEFAULTS, **(params or {})}
        self.fetcher = get_fetcher()
        self.analyzer = get_analyzer()
        self.watchlist = WatchlistManager()
        self.alerts = AlertManager()

    def check_all(self) -> List[Dict[str, Any]]:
        """
        检查所有自选股
        返回触发的信号列表
        """
        logger.info("开始检查自选股...")

        watchlist = self.watchlist.list()
        if not watchlist:
            logger.info("自选列表为空")
            return []

        signals = []

        for item in watchlist:
            try:
                code = item['code']
                alerts = self._check_stock(code, item)
                signals.extend(alerts)
            except Exception as e:
                logger.error(f"检查 {item.get('code')} 失败: {e}")

        logger.info(f"检查完成，发现 {len(signals)} 个信号")
        return signals

    def _check_stock(self, code: str, info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查单只股票"""
        signals = []

        try:
            # 获取实时数据
            realtime = self.fetcher.get_realtime(code)
            if not realtime:
                logger.debug(f"获取 {code} 实时数据失败")
                return signals

            price = realtime.get('price', 0)
            change_pct = realtime.get('change_pct', 0)

            # 更新自选股价格
            self.watchlist.update_price(code, price)

            # 1. 检查止损止盈
            buy_price = info.get('buy_price')
            if buy_price:
                stop_loss = info.get('stop_loss')
                target_price = info.get('target_price')

                if stop_loss and price <= stop_loss:
                    signal = self._create_signal(
                        code, "止损", "warning",
                        f"价格${price}触及止损价${stop_loss}",
                        f"建议卖出止损"
                    )
                    signals.append(signal)
                    self.alerts.add_alert(signal)

                if target_price and price >= target_price:
                    signal = self._create_signal(
                        code, "止盈", "success",
                        f"价格${price}达到目标价${target_price}",
                        f"建议分批止盈"
                    )
                    signals.append(signal)
                    self.alerts.add_alert(signal)

            # 2. 检查涨跌幅异常
            trigger_cfg = self.params.get("trigger_on", {})
            threshold = self.params.get("volume_spike_ratio", 2.0)

            if abs(change_pct) >= 9.5:
                # 涨停/跌停
                if change_pct > 0:
                    signal = self._create_signal(
                        code, "涨停", "info",
                        f"股票涨停！当前价格: {price}",
                        "关注封单变化，决定是否持有"
                    )
                else:
                    signal = self._create_signal(
                        code, "跌停", "danger",
                        f"股票跌停！当前价格: {price}",
                        "注意风险，考虑止损"
                    )
                signals.append(signal)
                self.alerts.add_alert(signal)

            elif abs(change_pct) >= 5:
                # 大幅波动
                direction = "上涨" if change_pct > 0 else "下跌"
                signal = self._create_signal(
                    code, f"大幅{direction}", "warning" if change_pct < 0 else "info",
                    f"{direction} {abs(change_pct):.2f}%，价格: {price}",
                    "关注是否延续趋势"
                )
                signals.append(signal)
                self.alerts.add_alert(signal)

            # 3. 获取技术分析
            try:
                analysis = self.analyzer.analyze(code)
                if "error" not in analysis:
                    signal_info = self._check_technical_signals(code, analysis)
                    if signal_info:
                        signals.append(signal_info)
                        self.alerts.add_alert(signal_info)
            except Exception as e:
                logger.debug(f"技术分析失败 {code}: {e}")

        except Exception as e:
            logger.error(f"检查股票 {code} 异常: {e}")

        return signals

    def _check_technical_signals(self, code: str, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """检查技术信号"""
        tech = analysis.get("技术面", {})
        macd = tech.get("MACD", {})
        kdj = tech.get("KDJ", {})

        # MACD金叉/死叉
        if macd.get("交叉信号") == "金叉":
            return self._create_signal(
                code, "MACD金叉", "success",
                "MACD在0轴附近形成金叉",
                "短线看多信号，可考虑买入"
            )

        if macd.get("交叉信号") == "死叉":
            return self._create_signal(
                code, "MACD死叉", "danger",
                "MACD形成死叉",
                "短线看空信号，考虑减仓"
            )

        # KDJ超买超卖
        if kdj.get("信号") == "超卖":
            return self._create_signal(
                code, "KDJ超卖", "success",
                "KDJ进入超卖区域",
                "可能出现反弹，关注"
            )

        if kdj.get("信号") == "超买":
            return self._create_signal(
                code, "KDJ超买", "warning",
                "KDJ进入超买区域",
                "警惕回调风险"
            )

        return None

    def _create_signal(self, code: str, signal_type: str, level: str,
                      message: str, suggestion: str) -> Dict[str, Any]:
        """创建信号对象"""
        return {
            "code": code,
            "type": signal_type,
            "level": level,
            "message": message,
            "suggestion": suggestion,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }


# 单例
_monitor_instance = None

def get_monitor(params: Dict[str, Any] = None) -> StockMonitor:
    """获取监控器单例"""
    global _monitor_instance
    if _monitor_instance is None or params:
        _monitor_instance = StockMonitor(params)
    return _monitor_instance
