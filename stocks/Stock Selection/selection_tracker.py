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

def _get_fetcher():
    global _fetcher
    if _fetcher is None:
        from data_fetcher import get_fetcher
        _fetcher = get_fetcher()
    return _fetcher


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

    def add_weekly_watchlist(self, stocks: List[Dict[str, Any]]):
        """记录每周自选股（同时生成出击股票）"""
        data = self._load()
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data["最后更新"] = today
        data["本周自选股"] = []
        data["加仓股票"] = []
        data["出击股票"] = []  # 从加仓股票中精选的前5只

        buy_signals = ["加仓", "买入", "强烈推荐"]

        for stock in stocks:
            code = stock.get("code", "")
            # 获取股票名称
            name = stock.get("name", "")
            if not name:
                try:
                    info = _get_fetcher().get_stock_info(code)
                    name = info.get("name", "") if info else ""
                except Exception:
                    name = ""

            stock_info = {
                "代码": code,
                "名称": name,
                "评级": stock.get("评级", ""),
                "信号": stock.get("信号", ""),
                "评分": stock.get("总分", 0),
                "最新价": stock.get("最新价", 0),
                "涨跌幅": stock.get("涨跌幅", 0),
                "止损": stock.get("止损", ""),
                "止盈": stock.get("止盈", ""),
                "理由": stock.get("理由", []),
            }
            data["本周自选股"].append(stock_info)

            # 同时记录加仓股票
            if stock.get("信号", "") in buy_signals:
                data["加仓股票"].append(stock_info)

        # 从加仓股票中精选出击股票：评分>=65，最多5只
        buyable = [s for s in data["加仓股票"] if s["评分"] >= 65]
        buyable.sort(key=lambda x: x["评分"], reverse=True)
        data["出击股票"] = buyable[:5]

        self._save(data)
        logger.info(f"已记录本周自选股 {len(stocks)} 只，其中出击 {len(data['出击股票'])} 只")

    def add_buy_signal(self, stocks: List[Dict[str, Any]]):
        """记录每日加仓股票"""
        data = self._load()
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "每日加仓记录" not in data:
            data["每日加仓记录"] = []

        # 添加新的加仓记录
        for stock in stocks:
            buy_info = {
                "日期": today,
                "代码": stock.get("code", ""),
                "信号": stock.get("信号", ""),
                "评分": stock.get("总分", 0),
                "止损位": stock.get("止损", ""),
                "止盈位": stock.get("止盈", ""),
                "理由": stock.get("理由", []),
                "最新价": stock.get("最新价", 0),
            }
            data["每日加仓记录"].append(buy_info)

        self._save(data)
        logger.info(f"已记录今日加仓股票 {len(stocks)} 只")

    def update_position(self, code: str, entry_price: float, stop_loss: float,
                       take_profit: float, reason: str):
        """更新持仓信息"""
        data = self._load()
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "持仓记录" not in data:
            data["持仓记录"] = []

        # 检查是否已存在
        found = False
        for pos in data["持仓记录"]:
            if pos["代码"] == code:
                pos["持仓日期"] = today
                pos["持仓价"] = entry_price
                pos["止损位"] = stop_loss
                pos["止盈位"] = take_profit
                pos["持仓理由"] = reason
                found = True
                break

        if not found:
            data["持仓记录"].append({
                "代码": code,
                "名称": "",
                "持仓日期": today,
                "持仓价": entry_price,
                "当前价": entry_price,
                "止损位": stop_loss,
                "止盈位": take_profit,
                "持仓理由": reason,
                "状态": "持仓中"
            })

        self._save(data)
        logger.info(f"已更新持仓记录: {code}")

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
        if 出击:
            lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"今日可出击股票共有 {len(出击)} 只")
            lines.append("")
            for i, s in enumerate(出击, 1):
                code = s.get('代码', s.get('code', ''))
                name = STOCK_NAMES.get(code, s.get('name', ''))
                rating = s.get('评级', s.get('rating', ''))
                score = s.get('评分', s.get('总分', s.get('score', 0)))
                signal = s.get('信号', s.get('signal', ''))
                # 最佳买入区间 = 最新价上下1%（收紧买入区间降低风险）
                price = s.get('最新价', s.get('price', 0))
                buy_range = f"{price*0.99:.2f}-{price*1.01:.2f}" if price else ""
                take_profit = s.get('止盈', s.get('止盈位', s.get('take_profit', '')))
                stop_loss = s.get('止损', s.get('止损位', s.get('stop_loss', '')))
                # 止盈止损依据
                sl_tp_reason = s.get('止盈止损依据', '')
                if sl_tp_reason:
                    lines.append(f"    止盈止损依据: {sl_tp_reason}")
                reasons = s.get('理由', s.get('reasons', []))
                reason_str = '，'.join(reasons) if isinstance(reasons, list) else str(reasons)

                lines.append(f"【{i}】{code} {name}")
                lines.append(f"    评级: {rating}")
                lines.append(f"    评分: {score:.1f}")
                lines.append(f"    信号: {signal}")
                lines.append(f"    最佳买入区间: {buy_range}")
                lines.append(f"    止盈位: {take_profit}")
                lines.append(f"    止损位: {stop_loss}")
                lines.append(f"    买入理由: {reason_str}")
                lines.append("")

        lines.append("")
        return "\n".join(lines)

    def save_report(self):
        """保存报告到文件"""
        report = self.generate_report()
        report_file = self.tracker_file.parent / "出击.报告.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"报告已保存到: {report_file}")

    def save_weekly_watchlist(self, stocks: List[Dict[str, Any]]):
        """保存自选股池到weekly_watchlist.txt（代码+名称，用于备份复盘）"""
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        lines.append(f"共 {len(stocks)} 只股票\n")

        # 保留代码和名称
        for stock in stocks:
            code = stock.get('code', '')
            name = STOCK_NAMES.get(code, stock.get('name', ''))
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