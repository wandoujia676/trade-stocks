"""
选股引擎 - 基于书籍理论的量化选股规则
支持多因素评分模型
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
import numpy as np

from config import SCREENER_DEFAULTS, SECTOR_MAP
from data_fetcher import get_fetcher, get_news_fetcher, DataQualityError
from warfare import get_warfare

logger = logging.getLogger(__name__)


class StockScreener:
    """
    智能选股引擎

    选股逻辑基于以下书籍理论：
    - 《短线操盘》：强势股、题材热点、缺口理论
    - 《股市扫地僧》：科学选股、只做强势股
    - 《交易真相》：概率思维、趋势跟随
    - 《量学》：量柱理论、黄金柱
    """

    def __init__(self, params: Dict[str, Any] = None):
        self.params = {**SCREENER_DEFAULTS, **(params or {})}
        self.fetcher = get_fetcher()
        self._last_screen_stats = None  # 最近一次选股的实时数据获取统计

    def screen(self, market: str = "全市场", limit: int = 20, realtime: bool = None) -> List[Dict[str, Any]]:
        """
        执行选股筛选

        Args:
            market: 市场范围 (全市场/创业板/科创板/主板)
            limit: 返回数量限制
            realtime: True=强制实时模式, False=强制完整模式, None=自动判断

        Returns:
            筛选后的股票列表，按评分排序
        """
        # 自动判断是否使用实时模式
        if realtime is None:
            realtime = self._should_use_realtime()

        if realtime:
            logger.info(f"开始实时选股，市场: {market}, 限制: {limit}")
            return self._screen_realtime(market, limit)
        else:
            logger.info(f"开始完整选股，市场: {market}, 限制: {limit}")
            return self._screen_full(market, limit)

    def _should_use_realtime(self) -> bool:
        """
        自动判断是否应该使用实时模式

        Returns:
            True 如果当前在交易时间内
        """
        try:
            return self.fetcher.is_market_open()
        except Exception:
            return False

    def _screen_realtime(self, market: str, limit: int) -> List[Dict[str, Any]]:
        """
        实时选股模式 - 盘中使用实时数据

        流程:
        1. 获取候选股票池
        2. 批量获取实时行情
        3. 快速筛选（基于实时指标）
        4. 对通过的候选获取历史数据 + 实时评分
        """
        # ============ 步骤0: 大盘趋势判断（李成刚：顺势而为）============
        print("\n========== 大盘趋势判断 ==========")
        market_trend = self._get_market_trend()
        print(f"大盘趋势: {market_trend['趋势']} ({market_trend['评分']}分)")
        print(f"仓位建议: {market_trend['仓位建议']}")
        if market_trend.get("原因"):
            for reason in market_trend["原因"]:
                print(f"  - {reason}")
        print(f"建议: {market_trend['建议']}")
        print("=" * 40)

        # 【v8.3新增】大盘下降趋势时直接返回空
        if market_trend.get("趋势") == "下降":
            print("【v8.3整改】大盘下降趋势，停止选股，等待企稳")
            return []

        # 步骤1: 获取候选股票池
        candidates = self._get_candidate_pool(market)
        if not candidates:
            logger.warning("候选股票池为空")
            return []

        logger.info(f"候选股票数量: {len(candidates)}")

        # 步骤2: 批量获取实时行情
        logger.info("获取实时行情...")
        spots_df = self.fetcher.get_realtime_batch(candidates)

        if spots_df is None or spots_df.empty:
            # 【v7.4 强制实时】不降级到日线模式，记录失败并由 cli.py 处理
            logger.warning("实时行情获取失败（新浪/腾讯均不可用）")
            self._last_screen_stats = {
                "candidates": len(candidates),
                "spots_fetched": 0,
                "realtime_mode": True,
                "data_source": "失败",
            }
            return []

        # 转换为dict便于处理
        spots = {}
        for _, row in spots_df.iterrows():
            spots[row['code']] = row.to_dict()

        logger.info(f"获取到 {len(spots)} 只股票的实时行情")

        # 判断实际使用的数据源（新浪成功还是降级到腾讯）
        data_source = "sina"
        if spots_df is not None and not spots_df.empty and 'source' in spots_df.columns:
            data_source = spots_df['source'].iloc[0]
        data_source_cn = "新浪" if data_source == "sina" else "腾讯"

        # 记录实时数据获取统计（供 cli.py 做覆盖率检查）
        self._last_screen_stats = {
            "candidates": len(candidates),
            "spots_fetched": len(spots),
            "realtime_mode": True,
            "data_source": data_source_cn,
        }
        coverage = len(spots) / len(candidates) * 100 if candidates else 0
        logger.info(f"实时数据覆盖率: {coverage:.1f}% ({len(spots)}/{len(candidates)})，数据源: {data_source_cn}")

        # 步骤3: 快速筛选（基于实时指标）
        # 李成刚核心：买跌不买涨，排除追高
        # - 涨幅过滤: -5%~15%（排除大涨大跌）
        # - 量比过滤: >=1.0
        # - 换手率: >=3% (如果可获取)
        quick_filtered = []
        for code, spot in spots.items():
            try:
                pct_chg = float(spot.get('pct_chg', 0))  # 注意：不取绝对值
                volume = int(spot.get('volume', 0))

                # 李成刚原则：排除大涨（>15%）和大跌（<-10%）
                if pct_chg > 20:  # 超过20%基本是涨停或大涨，不符合左侧
                    continue
                if pct_chg < -10:  # 跌幅过大可能是弱势股
                    continue
                if volume < 100000:  # 成交量太小
                    continue

                quick_filtered.append(code)
            except (ValueError, TypeError):
                continue

        logger.info(f"快速筛选后剩余: {len(quick_filtered)} 只")

        if not quick_filtered:
            # 如果没有满足条件的，返回所有有实时数据的股票
            quick_filtered = list(spots.keys())[:50]

        # 【v8.0优化】步骤3.5: 批量预取新闻数据（仅获取快讯，避免API超时）
        news_cache = {}
        try:
            news_fetcher = get_news_fetcher()
            if news_fetcher.is_available():
                # 只获取市场快讯（快，不超时），通过关键词匹配个股
                general_news = news_fetcher.get_general_news(limit=50)
                if not general_news.empty:
                    # 按关键词分发新闻到相关个股
                    for _, row in general_news.iterrows():
                        content = str(row.get('content', '')) + str(row.get('keyword', ''))
                        for code in quick_filtered[:30]:
                            if code in news_cache:
                                continue  # 已分配过的跳过
                            # 简单匹配：新闻中出现代码或名称关键词
                            if code in content:
                                if news_cache.get(code, {}).get('count', 0) < 3:
                                    news_cache.setdefault(code, {'count': 0, 'keywords': []})
                                    news_cache[code]['count'] += 1
                                    news_cache[code]['keywords'].append(str(row.get('keyword', ''))[:20])
                logger.info(f"预取新闻数据: {len(news_cache)} 只")
        except Exception as e:
            logger.debug(f"新闻预取失败: {e}")

        # 【v9.0 Step 2】步骤3.5: 批量预取基本面/资金面/催化剂数据
        fundamental_cache = {}
        moneyflow_cache = {}
        catalyst_cache = {}
        targets = quick_filtered[:100]
        if targets:
            print(f"\n步骤3.5: 批量预取基本面/资金面/催化剂数据（{len(targets)} 只）")
            for code in targets:
                try:
                    fundamental_cache[code] = self.fetcher.get_financial_indicators(code)
                except Exception as e:
                    logger.debug(f"基本面预取失败 {code}: {e}")
                try:
                    moneyflow_cache[code] = self.fetcher.get_moneyflow(code, days=5)
                except Exception as e:
                    logger.debug(f"资金面预取失败 {code}: {e}")
                try:
                    catalyst_cache[code] = self.fetcher.get_catalysts(code)
                except Exception as e:
                    logger.debug(f"催化剂预取失败 {code}: {e}")
            logger.info(
                f"v9.0 Step 2 预取: 基本面 {sum(1 for v in fundamental_cache.values() if v)} 只 / "
                f"资金面 {sum(1 for v in moneyflow_cache.values() if v)} 只 / "
                f"催化剂 {sum(1 for v in catalyst_cache.values() if v)} 只"
            )

        # 步骤4: 获取历史数据 + 实时评分
        scored = []
        for code in quick_filtered[:100]:  # 限制处理数量
            try:
                realtime_data = spots.get(code)
                if not realtime_data:
                    continue

                # 获取历史日线数据（用于计算技术指标）
                df_history = self.fetcher.get_daily(code, use_cache=True)
                if df_history is None or len(df_history) < 20:
                    continue

                # 将预取新闻数据注入 realtime_data（供 warfare 使用）
                eval_data = dict(realtime_data)
                eval_data['code'] = code
                if code in news_cache:
                    eval_data['_news_sentiment'] = news_cache[code]
                # 【v9.0 Step 2】注入基本面/资金面/催化剂数据
                if code in fundamental_cache:
                    eval_data['_fundamentals'] = fundamental_cache[code]
                    # PE 补充：stock_financial_abstract_ths 不含PE，从实时行情取
                    if eval_data['_fundamentals'].get('pe') is None and realtime_data:
                        pe_val = realtime_data.get('市盈率-动态')
                        if pe_val is not None:
                            try:
                                eval_data['_fundamentals']['pe'] = float(pe_val)
                            except (ValueError, TypeError):
                                pass
                if code in moneyflow_cache:
                    eval_data['_moneyflow'] = moneyflow_cache[code]
                if code in catalyst_cache:
                    eval_data['_catalysts'] = catalyst_cache[code]

                # 调用实时评估（纯左侧战法 v8.0）
                warfare = get_warfare()
                result = warfare.evaluate_realtime(df_history, eval_data, mode="left")

                if "error" in result:
                    continue

                # 提取评分
                composite = result.get("综合", {}).get("评分", 0)
                signal = result.get("信号", {})
                breakout = result.get("启动信号", {})

                scored.append({
                    "代码": code,
                    "名称": realtime_data.get('name', ''),
                    "评级": result.get("综合", {}).get("评级", "B"),
                    "信号": signal.get("操作", "持有"),
                    "总分": composite,
                    "趋势": result.get("趋势", {}).get("评分", 0),
                    "动量": result.get("动量", {}).get("评分", 0),
                    "量价": result.get("量价", {}).get("评分", 0),
                    "量在价先": result.get("量在价先", {}).get("评分", 0),
                    "热点消息": result.get("热点消息", {}).get("评分", 0),
                    "形态": result.get("形态", {}).get("评分", 0),
                    "位置": result.get("位置", {}).get("评分", 0),
                    "情绪": result.get("情绪", {}).get("评分", 0),
                    "最新价": realtime_data.get('current', 0),
                    "涨跌幅": realtime_data.get('pct_chg', 0),
                    "止损": signal.get("止损", "8%"),
                    "止盈": signal.get("止盈", "10%"),
                    "理由": signal.get("理由", []),
                    "分级": signal.get("分级", "备用"),
                    "仓位建议": signal.get("仓位建议", ""),
                    "启动信号": breakout.get("启动信号", False),
                    "启动强度": breakout.get("信号强度", "无"),
                    "实时模式": True,
                    "更新时间": realtime_data.get('update_time', ''),
                })
            except Exception as e:
                logger.debug(f"评估 {code} 失败: {e}")
                continue

        # 步骤5: 过滤和排序
        scored = [s for s in scored if "加仓" in s.get("信号", "") or "买入" in s.get("信号", "")]

        # 【v8.0新增】步骤6: 应用板块轮动加成
        scored = self._apply_sector_rotation_bonus(scored)

        # 添加大盘趋势信息（李成刚：顺势而为）
        for stock in scored:
            stock["大盘趋势"] = market_trend["趋势"]
            stock["建议仓位"] = market_trend["仓位建议"]

        scored.sort(key=lambda x: x["总分"], reverse=True)

        # 【v9.0新增】步骤7: 左侧强信号自动入观察池
        self._auto_add_to_observation_pool(scored)

        logger.info(f"实时选股完成，返回 {min(len(scored), limit)} 只")
        return scored[:limit]

    # ==================== 板块轮动分析 v8.0 ====================
    # 【v8.0 新增核心维度】
    # 核心理念：借板块之势——在热板轮动中选左侧股票，拉升更快
    # 今日热点板块的龙头股，更容易获得资金青睐

    def _get_hot_sectors(self) -> Tuple[set, dict]:
        """
        获取今日热门板块（通过涨跌停股票推断）

        Returns:
            (hot_sectors: set of sector names, sector_scores: dict of sector -> hot score)
            如果失败，返回 (empty set, empty dict)
        """
        hot_sectors = set()
        sector_scores = {}  # 板块 -> 热度得分

        try:
            news_fetcher = get_news_fetcher()
            if not news_fetcher.is_available():
                return hot_sectors, sector_scores

            # 获取今日涨停原因分析（反映热点板块）
            today = datetime.now().strftime("%Y%m%d")
            limit_df = news_fetcher.get_limit_up_reason(trade_date=today)
            if limit_df is None or limit_df.empty:
                # 尝试获取市场快讯作为热点参考
                news_df = news_fetcher.get_general_news(limit=30)
                if news_df is None or news_df.empty:
                    return hot_sectors, sector_scores

                # 从新闻关键词推断热点
                hot_keywords = ["科技", "新能源", "医药", "消费", "芯片", "人工智能",
                               "半导体", "军工", "光伏", "锂电池", "储能", "电动车"]
                sector_keyword_count = {}
                for _, row in news_df.iterrows():
                    content = str(row.get('content', '')) + str(row.get('keyword', ''))
                    for kw in hot_keywords:
                        if kw in content:
                            sector_keyword_count[kw] = sector_keyword_count.get(kw, 0) + 1

                for sector, count in sector_keyword_count.items():
                    if count >= 2:
                        hot_sectors.add(sector)
                        sector_scores[sector] = min(count * 5, 25)  # 最高25分

                return hot_sectors, sector_scores

            # 从涨停原因中提取热点板块
            for _, row in limit_df.iterrows():
                reason = str(row.get('reason', ''))
                # 提取板块关键词
                hot_keywords = ["科技", "新能源", "医药", "消费", "芯片", "人工智能",
                               "半导体", "军工", "光伏", "锂电池", "储能", "电动车",
                               "汽车", "地产", "金融", "证券", "化工", "次新"]
                for kw in hot_keywords:
                    if kw in reason:
                        hot_sectors.add(kw)
                        sector_scores[kw] = sector_scores.get(kw, 0) + 5

            logger.info(f"今日热门板块: {list(hot_sectors)[:5]}")

        except Exception as e:
            logger.debug(f"获取热门板块失败: {e}")

        return hot_sectors, sector_scores

    def _get_stock_sector(self, code: str) -> str:
        """
        获取个股所属板块（通过名称/概念推断）

        Returns:
            板块名称，如果没有找到返回 ""
        """
        try:
            info = self.fetcher.get_stock_info(code)
            name = info.get('name', '') or info.get('股票名称', '')

            # 通过名称关键词匹配板块
            sector_keywords = {
                "新能源": ["新能源", "锂电", "光伏", "储能", "电动车", "汽车"],
                "科技": ["科技", "软件", "芯片", "半导体", "人工智能", "AI", "智能"],
                "消费": ["消费", "食品", "白酒", "家电", "旅游", "零售"],
                "医药": ["医药", "医疗", "生物", "中药", "疫苗", "健康"],
                "金融": ["银行", "证券", "保险", "金融"],
                "周期": ["钢铁", "煤炭", "有色", "化工", "建材", "矿产"],
                "军工": ["军工", "航空", "航天", "船舶", "国防"],
            }

            for sector, keywords in sector_keywords.items():
                for kw in keywords:
                    if kw in name:
                        return sector

            return ""

        except Exception as e:
            logger.debug(f"获取个股板块失败 {code}: {e}")
            return ""

    def _apply_sector_rotation_bonus(self, scored: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        应用板块轮动加成 v8.0

        逻辑：
        - 股票属于今日热门板块 → +15分
        - 股票属于非热门但也不冷门的板块 → +5分
        - 股票属于冷门板块（不在热门列表）→ 不加分不扣分
        - 注意：不扣分（板块轮动是加分项，不是过滤项）
        """
        hot_sectors, sector_scores = self._get_hot_sectors()

        if not hot_sectors:
            # 如果无法获取热门板块，跳过加成
            return scored

        for stock in scored:
            code = stock.get('代码', '') or stock.get('code', '')
            stock_sector = self._get_stock_sector(code)
            stock['所属板块'] = stock_sector

            if stock_sector in hot_sectors:
                bonus = sector_scores.get(stock_sector, 15)
                stock['板块加成'] = bonus
                stock['板块状态'] = "热点"
                stock['总分'] = round(stock.get('总分', 0) + bonus, 1)
            else:
                stock['板块加成'] = 0
                stock['板块状态'] = "普通"

        return scored

    def _screen_full(self, market: str, limit: int) -> List[Dict[str, Any]]:
        """
        完整选股模式 - 盘后使用完整日线数据

        (原screen()逻辑)
        """
        # ============ 步骤0: 大盘趋势判断（李成刚：顺势而为）============
        print("\n========== 大盘趋势判断 ==========")
        market_trend = self._get_market_trend()
        print(f"大盘趋势: {market_trend['趋势']} ({market_trend['评分']}分)")
        print(f"仓位建议: {market_trend['仓位建议']}")
        if market_trend.get("原因"):
            for reason in market_trend["原因"]:
                print(f"  - {reason}")
        print(f"建议: {market_trend['建议']}")

        # 【v8.3整改】大盘下降趋势时直接返回空（不限制数量，直接停止）
        if market_trend.get("趋势") == "下降":
            print("【v8.3整改】大盘下降趋势，停止选股，等待企稳")
            return []

        # 根据大盘趋势调整选股数量
        adjusted_limit = self._get_position_limit(market_trend, limit)
        if adjusted_limit < limit:
            print(f"根据大盘趋势，调整选股数量: {limit} → {adjusted_limit}")
        print("=" * 40)

        # 步骤1: 获取候选股票池
        candidates = self._get_candidate_pool(market)
        if not candidates:
            logger.warning("候选股票池为空")
            return []

        logger.info(f"候选股票数量: {len(candidates)}")

        # 记录统计（盘后模式，非实时）
        self._last_screen_stats = {
            "candidates": len(candidates),
            "spots_fetched": len(candidates),  # 盘后模式全部获取
            "realtime_mode": False,
        }

        # 【v8.3新增】大盘下降趋势时直接返回空（不做左侧选股）
        if market_trend.get("趋势") == "下降":
            print("【v8.3整改】大盘下降趋势，停止选股，等待企稳")
            return []

        # 步骤2: 批量技术面筛选
        tech_passed = self._filter_technical(candidates)
        logger.info(f"技术面通过数量: {len(tech_passed)}")

        # 步骤3: 基本面筛选
        fund_passed = self._filter_fundamental(tech_passed)
        logger.info(f"基本面通过数量: {len(fund_passed)}")

        # 步骤4: 情绪面筛选
        sentiment_passed = self._filter_sentiment(fund_passed)
        logger.info(f"情绪面通过数量: {len(sentiment_passed)}")

        # 步骤5: 多因素评分
        scored = self._score_stocks(sentiment_passed)

        # 步骤6: 只保留加仓/买入信号（过滤减仓/观望）
        # 使用包含判断，因为信号可能是"持有/加仓"混合信号
        scored = [s for s in scored if "加仓" in s.get("信号", "") or "买入" in s.get("信号", "") or "强烈推荐" in s.get("信号", "")]

        # ============ 步骤7: 添加大盘趋势信息到结果 ============
        for stock in scored:
            stock["大盘趋势"] = market_trend["趋势"]
            stock["建议仓位"] = market_trend["仓位建议"]

        # 排序并返回
        scored.sort(key=lambda x: x["总分"], reverse=True)
        return scored[:adjusted_limit]

    def get_last_screen_stats(self) -> Optional[Dict[str, Any]]:
        """获取最近一次选股的实时数据获取统计"""
        return self._last_screen_stats

    def _get_candidate_pool(self, market: str) -> List[str]:
        """
        获取候选股票池
        优先从 monthly_candidate_pool.json 读取（带 筛选轨道 字段，供 v9.0 战法分发使用），
        失败则降级到 monthly_watchlist.txt（仅代码，无轨道）。
        """
        base_dir = Path(__file__).parent
        json_file = base_dir / "View Results" / "monthly_candidate_pool.json"
        monthly_file = base_dir / "View Results" / "monthly_watchlist.txt"

        codes = []
        track_map: Dict[str, str] = {}

        if json_file.exists():
            try:
                import json as _json
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = _json.load(f)
                for stock in data.get("股票列表", []):
                    code = stock.get("code", "")
                    if code and code.isdigit() and len(code) == 6:
                        codes.append(code)
                        track = stock.get("筛选轨道", "")
                        if track in ("left", "right"):
                            track_map[code] = track
                logger.info(
                    f"从 monthly_candidate_pool.json 读取到 {len(codes)} 只股票 "
                    f"(left={sum(1 for v in track_map.values() if v=='left')}, "
                    f"right={sum(1 for v in track_map.values() if v=='right')})"
                )
            except Exception as e:
                logger.warning(f"读取 monthly_candidate_pool.json 失败: {e}")
                codes = []

        if not codes and monthly_file.exists():
            try:
                with open(monthly_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # 匹配格式: "代码 - 名称 | 行业 | 评分:xx" 或 "代码 - 名称"
                        if line and not line.startswith("=") and not line.startswith("共") and not line.startswith("月度"):
                            parts = line.split(" - ")
                            if len(parts) >= 1:
                                code = parts[0].strip()
                                # 过滤非股票代码行
                                if code and code.isdigit() and len(code) == 6:
                                    codes.append(code)
                logger.info(f"从 monthly_watchlist.txt 读取到 {len(codes)} 只股票（无轨道信息）")
            except Exception as e:
                logger.warning(f"读取 monthly_watchlist.txt 失败: {e}")

        # 如果读取失败或文件不存在，使用 fallback 候选池
        if not codes:
            logger.warning("使用 fallback 候选池")
            codes = [
                # 银行
                "000001", "600016", "600036", "601166", "601288", "601328", "601398", "601818",
                # 证券
                "600030", "600837", "601066", "601211", "601688", "000776",
                # 保险
                "601318", "601601", "601628", "601336",
                # 白酒
                "000568", "000858", "600519", "603288",
                # 新能源
                "300750", "002594", "600438", "601012", "002466",
                # 科技龙头
                "000001", "000002", "000063", "000100", "002230", "002241",
                "002415", "002460", "300033", "300059", "300124",
                # 医药
                "000538", "600276", "603259", "300015", "002007",
                # 芯片/半导体
                "002371", "688981", "603501", "002236",
                # 消费电子
                "000725", "002241", "300866",
                # 互联网
                "300059", "300024", "603259",
            ]

        # 持久化 track_map 供后续 _filter_technical / _score_stocks 使用
        self._candidate_track_map = track_map

        # 根据市场筛选
        if market == "创业板":
            return [c for c in codes if c.startswith("300") and not c.startswith("688")]
        elif market == "科创板":
            return [c for c in codes if c.startswith("688")]
        elif market == "主板":
            return [c for c in codes if c.startswith(("600", "000", "001"))]
        else:  # 全市场
            return list(set(codes))  # 去重

    def _filter_technical(self, codes: List[str]) -> List[Dict[str, Any]]:
        """
        技术面筛选 - 优化版：让更多高动量股票通过

        修改：
        1. 放宽均线要求，不再硬性要求均线多头
        2. 降低成交量门槛
        3. 重点关注近期有涨幅的股票
        【v9.1 加固】失败率统计 + 熔断：数据拉取失败率 >50% 直接抛 DataQualityError
        """
        passed = []
        ma_params = self.params

        total = len(codes)
        fetch_failed = 0  # 数据拉取失败（区别于业务过滤淘汰）

        print(f"\n技术面筛选进度（{total}只）...")

        for i, code in enumerate(codes):
            try:
                df = self.fetcher.get_daily(code)
                if df is None or len(df) < 30:
                    fetch_failed += 1
                    continue

                # 转换为方便计算的格式
                df = df.tail(60).copy()  # 取近60天
                closes = df['close'].astype(float).values
                volumes = df['volume'].astype(float).values

                # ========== 计算各项指标 ==========
                # 均线
                ma5 = self._ma(closes, 5)
                ma10 = self._ma(closes, 10)
                ma20 = self._ma(closes, 20)

                # 5日涨幅（重点！）
                change_5d = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0

                # 10日涨幅
                change_10d = (closes[-1] - closes[-10]) / closes[-10] * 100 if len(closes) >= 10 else change_5d * 2

                # 量比
                vol_ratio = self._volume_ratio(volumes)

                # 平均成交量
                avg_vol = np.mean(volumes[-5:])
                avg_vol_20 = np.mean(volumes[-20:])

                # MACD
                macd, signal, hist = self._macd(closes)

                # ========== 筛选条件（大幅放宽）============

                # 条件1：成交量门槛（降低到5日均量>50万）
                if avg_vol < 50000:  # 50万
                    continue

                # 条件2：排除极度弱势（MACD在-2以下且均线空头）
                macd_val = macd[-1] if len(macd) > 0 else 0
                is_below_ma20 = closes[-1] < ma20[-1] if len(ma20) > 0 else False
                if macd_val < -2 and is_below_ma20:
                    continue

                # 条件3：排除长期下跌的股票（20日跌幅>30%）
                change_20d = (closes[-1] - closes[-20]) / closes[-20] * 100 if len(closes) >= 20 else 0
                if change_20d < -30:
                    continue

                # ========== 通过筛选，计算初步评分 ==========
                # 【v8.3整改】修复动量矛盾：
                # 预筛选打分和最终评分要一致，不能一个给跌的打分、另一个给涨的打分
                # 整改：预筛选聚焦"技术面健康度"，评分聚焦"动量启动"
                pre_score = 0

                # 1. 量能健康度（缩量是左侧信号，但要和评分一致）
                if vol_ratio < 0.5:
                    pre_score += 10  # 极度缩量，地量见底
                elif vol_ratio < 0.7:
                    pre_score += 7   # 缩量
                elif vol_ratio < 1.0:
                    pre_score += 3   # 轻度缩量
                elif vol_ratio >= 2.5:
                    pre_score -= 5   # 异常放量，需确认

                # 2. 均线位置（价格在均线附近=正常，过高/过低都要扣分）
                if len(ma5) > 0:
                    ma5_dist = (closes[-1] - ma5[-1]) / ma5[-1] * 100
                    if abs(ma5_dist) < 3:
                        pre_score += 8   # 贴近MA5，最佳位置
                    elif ma5_dist < -10:
                        pre_score += 5   # 偏离MA5下方较多，左侧信号（但降低权重）
                    elif ma5_dist > 10:
                        pre_score -= 5   # 偏离MA5上方，追高风险

                if len(ma20) > 0:
                    ma20_dist = (closes[-1] - ma20[-1]) / ma20[-1] * 100
                    if ma20_dist < -15:
                        pre_score += 5   # 严重偏离MA20下方，左侧信号
                    elif ma20_dist > 15:
                        pre_score -= 5   # 严重偏离MA20上方，追高风险

                # 3. MACD状态（DIF在0轴附近最佳，过低说明很弱）
                if macd_val > 0:
                    pre_score += 5    # 已在0轴上方，右侧健康
                elif macd_val > -0.5:
                    pre_score += 10   # DIF在0轴附近，即将金叉，最佳左侧买点
                elif macd_val > -1.5:
                    pre_score += 5    # DIF在0轴下方，不算太差
                # macd_val < -1.5: 不加分，说明很弱

                # 4. 趋势健康度（不是单边下跌的股票）
                if change_5d >= -5 and change_5d <= 10:
                    pre_score += 10  # 区间震荡，最健康
                elif change_5d > 10:
                    pre_score -= 3   # 近期涨幅过大，追高风险
                elif change_5d < -15:
                    pre_score -= 5   # 【v8.3降低】跌幅过大，可能是接飞刀

                # 5. 排除明显下跌趋势（20日均线空头）
                # 【v9.1 step6d】只对 right/未知 候选生效；left 候选的"均线空头+近期下跌"
                # 恰恰是超跌反弹入场条件（参 warfare._evaluate_trend_left "均线蓄势/收敛"），
                # 用右侧规则一刀切会把真正的左侧买点全刷掉（如 605599 / 002379 基本面优质
                # 却被卡在这一关）。
                track_map = getattr(self, "_candidate_track_map", {}) or {}
                _track = track_map.get(code, "")
                if _track != "left" and len(ma5) > 0 and len(ma20) > 0:
                    if ma5[-1] < ma20[-1] * 0.97:  # MA5明显低于MA20
                        if change_5d < -5:
                            continue  # 均线空头+近期下跌 = 明确下跌趋势，放弃

                passed.append({
                    "code": code,
                    "data": df,
                    "track": _track,  # left / right / "" (未知)
                    "metrics": {
                        "5日涨幅": round(change_5d, 2),
                        "10日涨幅": round(change_10d, 2),
                        "量比": round(vol_ratio, 2),
                        "pre_score": pre_score,
                    }
                })

                # 每10只显示进度
                if (i + 1) % 10 == 0:
                    print(f"  已处理 {i+1}/{len(codes)}，通过 {len(passed)} 只")

            except Exception as e:
                fetch_failed += 1
                logger.debug(f"技术面筛选 {code} 失败: {e}")
                continue

        # 【v9.1】失败率熔断：数据层大面积失败时，大声报错而不是静默返回空
        failure_rate = fetch_failed / total if total > 0 else 0
        if total >= 10 and failure_rate > 0.5:
            raise DataQualityError(
                f"技术面数据拉取失败率 {failure_rate:.0%}（{fetch_failed}/{total}），"
                f"超过 50% 熔断阈值，疑似数据源大面积不可用"
            )
        if fetch_failed > 0:
            logger.warning(
                f"技术面数据拉取：{total - fetch_failed}/{total} 成功，"
                f"{fetch_failed} 失败（失败率 {failure_rate:.0%}）"
            )

        print(f"  技术面筛选完成：通过 {len(passed)} 只")
        return passed

    def _filter_fundamental(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        基本面筛选 - v8.3整改版：强化基本面，无法获取时降级不通过

        整改内容：
        1. 无法获取基本面数据 → 标记为低优先级（排在后面）
        2. 增加 PE 过滤（排除亏损股和高估值）
        3. 增加 ROE 过滤（排除低质量公司）
        4. 增加负债率过滤（排除高杠杆风险）
        """
        min_market_cap = self.params.get("市值_min", 30)  # 亿，提高到30亿
        max_pe = 80  # PE上限（排除亏损股和高估值）
        min_roe = 5  # ROE下限（%）
        max_debt_ratio = 70  # 负债率上限（%）

        passed = []
        low_priority = []  # 【v8.3新增】无法获取基本面的股票
        for item in candidates:
            try:
                info = self.fetcher.get_stock_info(item["code"])

                # 【v8.3整改】无法获取基本面数据 → 不通过（降级处理）
                if not info:
                    low_priority.append(item)
                    continue

                # 市值检查
                if "总市值" in info:
                    market_cap_str = info["总市值"]
                    if "亿" in market_cap_str:
                        cap = float(market_cap_str.replace("亿", "").replace("万", ""))
                        if cap < min_market_cap:
                            low_priority.append(item)
                            continue

                # 【v8.2新增】PE检查（排除亏损股）
                pe_ratio = info.get("pe_ratio") or info.get("市盈率")
                if pe_ratio is not None:
                    try:
                        pe_val = float(str(pe_ratio).replace("万", "").replace("亿", ""))
                        if pe_val <= 0 or pe_val > max_pe:  # 亏损(<=0)或高估值(>80)
                            low_priority.append(item)
                            continue
                    except (ValueError, TypeError):
                        low_priority.append(item)
                        continue

                # 【v8.2新增】ROE检查（排除低质量公司）
                roe = info.get("roe") or info.get("净资产收益率")
                if roe is not None:
                    try:
                        roe_val = float(str(roe).replace("%", ""))
                        if 0 < roe_val < min_roe:  # ROE过低
                            low_priority.append(item)
                            continue
                    except (ValueError, TypeError):
                        low_priority.append(item)
                        continue

                # 【v8.2新增】负债率检查（排除高杠杆）
                debt_ratio = info.get("debt_ratio") or info.get("资产负债率")
                if debt_ratio is not None:
                    try:
                        dr_val = float(str(debt_ratio).replace("%", ""))
                        if dr_val > max_debt_ratio:  # 负债率过高
                            low_priority.append(item)
                            continue
                    except (ValueError, TypeError):
                        low_priority.append(item)
                        continue

                passed.append(item)
            except Exception:
                low_priority.append(item)
                continue

        # 【v8.3整改】把低优先级股票加到末尾（但不在回测中使用）
        for item in low_priority:
            item["_low_priority"] = True  # 标记，用于后续过滤
            passed.append(item)

        return passed

    def _filter_sentiment(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """情绪面筛选"""
        passed = []

        for item in candidates:
            try:
                df = item["data"]
                if df is None or len(df) < 10:
                    continue

                # 检查近期是否有涨停
                pct_changes = df['pct_change'].astype(float).tail(10)
                has_recent_limit_up = (pct_changes >= 9.5).any()

                # 检查是否在近期高点附近
                recent_high = df['high'].astype(float).tail(20).max()
                current_price = df['close'].astype(float).iloc[-1]
                near_high_ratio = current_price / recent_high

                # 情绪面通过条件：近期有涨停 OR 接近近期高点
                if has_recent_limit_up or near_high_ratio > 0.85:
                    item["metrics"]["情绪信号"] = "强" if has_recent_limit_up else "中"
                    passed.append(item)
                elif near_high_ratio > 0.75:
                    item["metrics"]["情绪信号"] = "弱"
                    passed.append(item)

            except Exception as e:
                logger.debug(f"情绪面筛选 {item['code']} 失败: {e}")
                continue

        return passed

    def _score_stocks(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        多因素评分（使用综合战法 + 动量加权 + 消息面情绪）

        v9.0 架构修复（2026-05-18）：
        - 层2：批量预取基本面/资金面/催化剂数据，通过 info 注入 warfare.evaluate
        - 层3：按候选 track 字段分发战法模式（left → 左侧12维 / right → 波段7维）
        """
        warfare = get_warfare()
        news_fetcher = get_news_fetcher()
        news_available = news_fetcher.is_available()

        # 【v9.0 层2】批量预取三维度数据（仅对 left 候选；right 战法不消费这些字段）
        left_codes = [c["code"] for c in candidates if c.get("track") == "left"]
        fundamental_cache: Dict[str, Any] = {}
        moneyflow_cache: Dict[str, Any] = {}
        catalyst_cache: Dict[str, Any] = {}

        if left_codes:
            print(f"\n步骤3.5: 批量预取基本面/资金面/催化剂数据（{len(left_codes)} 只 left 候选）")
            for code in left_codes:
                try:
                    fundamental_cache[code] = self.fetcher.get_financial_indicators(code)
                except Exception as e:
                    logger.debug(f"基本面预取失败 {code}: {e}")
                try:
                    moneyflow_cache[code] = self.fetcher.get_moneyflow(code, days=5)
                except Exception as e:
                    logger.debug(f"资金面预取失败 {code}: {e}")
                try:
                    catalyst_cache[code] = self.fetcher.get_catalysts(code)
                except Exception as e:
                    logger.debug(f"催化剂预取失败 {code}: {e}")
            logger.info(
                f"v9.0 Step 2 预取: 基本面 {sum(1 for v in fundamental_cache.values() if v)} 只 / "
                f"资金面 {sum(1 for v in moneyflow_cache.values() if v)} 只 / "
                f"催化剂 {sum(1 for v in catalyst_cache.values() if v)} 只"
            )

        scored = []
        for item in candidates:
            try:
                df = item["data"]
                if df is None:
                    continue

                # 量比过滤：确保成交量活跃（量价配合良好的前提）
                volume_ratio = item.get("metrics", {}).get("量比", 1.0)
                if volume_ratio < 1.3:
                    continue

                code = item.get("code", "")
                track = item.get("track", "")

                # 【v9.0 层3】按 track 分发战法模式
                # left → 12维含三新维度  right → 7维主升浪  未知 → 默认 wave
                mode = "left" if track == "left" else "wave"

                # 【v9.0 层2】构造 info 注入三维度数据
                info: Dict[str, Any] = {"code": code}
                if mode == "left":
                    if code in fundamental_cache:
                        info["_fundamentals"] = fundamental_cache[code]
                    if code in moneyflow_cache:
                        info["_moneyflow"] = moneyflow_cache[code]
                    if code in catalyst_cache:
                        info["_catalysts"] = catalyst_cache[code]

                # 使用综合战法评估
                warfare_result = warfare.evaluate(df, info=info, mode=mode)

                if "error" in warfare_result:
                    continue

                composite = warfare_result.get("综合", {})
                signal = warfare_result.get("信号", {})

                # 基础综合评分
                base_score = composite.get("评分", 50)

                # ========== 动量加权（v8.3整改）============
                # 【核心问题】之前的逻辑：给涨的股票加分，给跌的加分
                # 整改后：动量加权要看"趋势是否健康"，不是"涨了就加分"
                # - 小幅震荡上涨（0-5%）= 最健康，加分
                # - 大涨（>10%）= 可能追高，减分
                # - 小幅下跌（-5%~0）= 可接受，不加分不减分
                # - 大跌（<-10%）= 接飞刀风险，减分
                change_5d = item.get("metrics", {}).get("5日涨幅", 0)
                momentum_bonus = 0
                if 0 <= change_5d <= 5:
                    momentum_bonus = 10   # 小幅震荡，最健康
                elif 5 < change_5d <= 10:
                    momentum_bonus = 5    # 温和上涨，可接受
                elif change_5d > 10:
                    momentum_bonus = -5   # 涨幅过大，可能回调
                elif -5 <= change_5d < 0:
                    momentum_bonus = 0    # 微跌，正常
                elif -10 <= change_5d < -5:
                    momentum_bonus = -3   # 明显下跌，风险
                elif change_5d < -10:
                    momentum_bonus = -8   # 【v8.3】大跌减分，避免接飞刀

                # ========== 消息面情绪加权 (小金库 6.4) ==========
                sentiment_bonus = 0
                sentiment_signal = "无"
                sentiment_keywords = []
                risk_keywords = []

                if news_available:
                    try:
                        code = item.get("code", "")
                        sentiment_result = news_fetcher.analyze_sentiment(code)
                        sentiment_score = sentiment_result.get("score", 50)
                        sentiment_signal = sentiment_result.get("signal", "中性")
                        sentiment_keywords = sentiment_result.get("keywords", [])[:5]
                        risk_keywords = sentiment_result.get("risk_keywords", [])[:5]

                        # 情绪评分映射到加成
                        # 利好(65+) 加分，利空(35-)减分
                        if sentiment_score >= 65:
                            sentiment_bonus = 15
                        elif sentiment_score >= 60:
                            sentiment_bonus = 10
                        elif sentiment_score >= 55:
                            sentiment_bonus = 5
                        elif sentiment_score <= 35:
                            sentiment_bonus = -15
                        elif sentiment_score <= 40:
                            sentiment_bonus = -10
                        elif sentiment_score <= 45:
                            sentiment_bonus = -5
                    except Exception as e:
                        logger.debug(f"消息面分析失败 {item.get('code')}: {e}")

                # 最终评分 = 基础评分 + 动量加成 + 情绪加成
                final_score = base_score + momentum_bonus + sentiment_bonus

                # 提取战法各维度评分
                item["总分"] = final_score
                item["基础分"] = base_score
                item["动量加成"] = momentum_bonus
                item["情绪加成"] = sentiment_bonus
                item["情绪信号"] = sentiment_signal
                item["情绪关键词"] = sentiment_keywords
                item["风险关键词"] = risk_keywords
                item["评级"] = composite.get("评级", "B")
                # 【v9.1 step6c】保留全部维度分数（按 mode 完整记录，便于诊断）
                # 缺失维度（mode 不匹配）记 None 而非 50，避免误判
                _all_dims = [
                    "趋势", "动量", "左侧", "量价", "形态", "位置", "情绪",  # 共有/老 7 维
                    "量在价先", "热点消息", "基本面", "资金面", "催化剂",     # left 专属
                    "突破",                                                   # wave 专属
                ]
                for _dim in _all_dims:
                    _v = warfare_result.get(_dim)
                    item[f"{_dim}分"] = _v.get("评分") if isinstance(_v, dict) else None
                item["战法模式"] = warfare_result.get("战法模式", mode)

                # 信号
                item["信号"] = signal.get("操作", "持有")
                item["理由"] = signal.get("理由", [])
                item["止损"] = signal.get("止损", "5%")
                item["止盈"] = signal.get("止盈", "15%")

                # 止盈止损动态依据
                if signal.get("止盈止损依据"):
                    item["止盈止损依据"] = signal.get("止盈止损依据")

                # 新增：分级和启动信号
                item["分级"] = signal.get("分级", "")
                item["仓位建议"] = signal.get("仓位建议", "")
                item["启动信号"] = signal.get("启动信号", False)
                item["启动强度"] = signal.get("启动强度", "")

                # 明日买入条件（李成刚核心）
                item["明日买入条件"] = signal.get("明日买入条件", {})

                # 提取最新价格
                item["最新价"] = float(df['close'].iloc[-1])
                item["涨跌幅"] = float(df['pct_change'].iloc[-1]) if 'pct_change' in df.columns else 0

                scored.append(item)

            except Exception as e:
                logger.debug(f"评分 {item.get('code')} 失败: {e}")
                continue

        return scored

    def _calc_tech_score(self, df: pd.DataFrame) -> float:
        """技术面评分 (0-100)"""
        score = 50.0

        try:
            closes = df['close'].astype(float).values
            volumes = df['volume'].astype(float).values

            # 均线多头程度
            ma5 = self._ma(closes, 5)
            ma10 = self._ma(closes, 10)
            ma20 = self._ma(closes, 20)

            if ma5[-1] > ma10[-1] > ma20[-1]:
                score += 15
            elif ma5[-1] > ma10[-1]:
                score += 8

            # MACD强势
            macd, signal, hist = self._macd(closes)
            if macd[-1] > 0 and hist[-1] > 0:
                score += 15
            elif macd[-1] > 0:
                score += 8

            # 成交量活跃度
            vol_ratio = self._volume_ratio(volumes)
            if vol_ratio > 2:
                score += 10
            elif vol_ratio > 1.5:
                score += 5

            # 趋势强度（相对位置）
            high20 = df['high'].astype(float).tail(20).max()
            low20 = df['low'].astype(float).tail(20).min()
            if high20 > 0:
                price_pos = (closes[-1] - low20) / (high20 - low20)
                score += price_pos * 10

            # 近期涨幅
            pct_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) > 5 else 0
            if 3 < pct_5d < 15:
                score += 10  # 适度涨幅

        except Exception:
            pass

        return min(100, max(0, score))

    def _calc_fund_score(self, item: Dict[str, Any]) -> float:
        """基本面评分 (0-100)"""
        # 简化评分：使用情绪信号和其他可用信息
        score = 60.0

        metrics = item.get("metrics", {})
        turnover_rate = metrics.get("换手率", 0)

        # 高换手率往往意味着活跃
        if turnover_rate > 5:
            score += 15
        elif turnover_rate > 3:
            score += 8

        # 情绪信号
        sentiment = metrics.get("情绪信号", "弱")
        if sentiment == "强":
            score += 25
        elif sentiment == "中":
            score += 15

        return min(100, max(0, score))

    def _calc_sentiment_score(self, item: Dict[str, Any]) -> float:
        """情绪面评分 (0-100)"""
        score = 50.0

        metrics = item.get("metrics", {})
        情绪 = metrics.get("情绪信号", "弱")

        if 情绪 == "强":
            score = 90.0
        elif 情绪 == "中":
            score = 70.0

        return min(100, max(0, score))

    # ==================== 技术指标计算 ====================

    def _ma(self, prices: np.ndarray, period: int) -> np.ndarray:
        """计算移动平均线"""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        return np.convolve(prices, np.ones(period)/period, mode='valid')

    def _macd(self, prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算MACD"""
        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)
        macd = ema_fast - ema_slow
        signal_line = self._ema(macd, signal)
        histogram = macd - signal_line
        return macd, signal_line, histogram

    def _ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """计算指数移动平均"""
        if len(prices) < period:
            return np.full(len(prices), np.nan)
        alpha = 2 / (period + 1)
        ema = np.zeros_like(prices)
        ema[0] = prices[0]
        for i in range(1, len(prices)):
            ema[i] = alpha * prices[i] + (1 - alpha) * ema[i-1]
        return ema

    def _volume_ratio(self, volumes: np.ndarray) -> float:
        """计算量比（今日量/5日均量）"""
        if len(volumes) < 6:
            return 1.0
        today_vol = volumes[-1]
        avg_vol_5 = np.mean(volumes[-6:-1])
        return today_vol / avg_vol_5 if avg_vol_5 > 0 else 1.0

    def _has_limit_up(self, df: pd.DataFrame, days: int = 10) -> bool:
        """检查近N日是否有涨停"""
        try:
            pct = df['pct_change'].astype(float).tail(days)
            return (pct >= 9.5).any()
        except:
            return False

    # ==================== 大盘趋势判断（李成刚：顺势而为）====================

    def _get_market_trend(self) -> Dict[str, Any]:
        """
        判断大盘趋势（李成刚：顺势而为）

        核心：大盘处于上升趋势时，左侧买入成功率高
            大盘处于下降趋势时，降低仓位或放弃选股
        """
        trend = {
            "趋势": "震荡",  # 上升/震荡/下降
            "评分": 50,
            "建议": "正常选股",
            "仓位建议": "20%",
            "原因": []
        }

        try:
            # 使用沪深300指数（000300）或上证指数判断大盘
            index_code = "000300"  # 沪深300

            df = self.fetcher.get_daily(index_code, use_cache=False)
            if df is None or len(df) < 20:
                trend["原因"].append("无法获取大盘数据")
                return trend

            closes = df['close'].astype(float).values
            pct_changes = df['pct_change'].astype(float).values if 'pct_change' in df.columns else np.diff(closes) / closes[:-1] * 100

            # 计算各项指标
            ma5 = np.mean(closes[-5:])
            ma20 = np.mean(closes[-20:])

            current_price = closes[-1]
            change_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
            change_20d = (closes[-1] - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else 0

            # ============ 判断趋势 ============
            score = 50  # 基础分

            # 1. 均线判断
            if ma5 > ma20:
                score += 20
                trend["原因"].append("均线多头（5日>20日）")
            elif ma5 < ma20:
                score -= 10
                trend["原因"].append("均线空头（5日<20日）")

            # 2. 价格位置
            if current_price > ma20:
                score += 15
                trend["原因"].append("价格在20日均线上方")
            else:
                score -= 15
                trend["原因"].append("价格在20日均线下方")

            # 3. 近期涨跌
            if change_5d > 3:
                score += 15
                trend["原因"].append(f"5日涨幅{change_5d:.1f}%")
            elif change_5d < -3:
                score -= 15
                trend["原因"].append(f"5日跌幅{abs(change_5d):.1f}%")

            if change_20d > 5:
                score += 15
                trend["原因"].append(f"20日涨幅{change_20d:.1f}%")
            elif change_20d < -5:
                score -= 15
                trend["原因"].append(f"20日跌幅{abs(change_20d):.1f}%")

            trend["评分"] = max(0, min(100, score))

            # ============ 确定趋势和仓位建议 ============
            # 【v8.3整改】更严格的下降趋势判断标准
            # 只有同时满足以下条件才判定为"下降"：
            # 1. 均线空头（MA5 < MA20）
            # 2. 价格在MA20下方
            # 3. 近期明显下跌（5日跌>3%或20日跌>5%）
            if score >= 60:  # 上升趋势
                trend["趋势"] = "上升"
                trend["建议"] = "积极选股，左侧买入成功率高"
                trend["仓位建议"] = "正常仓位（20-30%）"
            elif score >= 40:  # 震荡趋势
                trend["趋势"] = "震荡"
                trend["建议"] = "精选个股，控制仓位"
                trend["仓位建议"] = "轻仓（10-20%）"
            else:  # 【v8.3整改】下降趋势：停止选股
                trend["趋势"] = "下降"
                trend["建议"] = "【停止选股】左侧战法在下降市中几乎必亏"
                trend["仓位建议"] = "空仓（0%）"
                trend["操作"] = "STOP"  # 特殊标记，告诉上层停止选股

        except Exception as e:
            logger.warning(f"大盘趋势判断失败: {e}")
            trend["原因"].append(f"判断失败: {str(e)}")

        return trend

    # ==================== 大盘过滤后的选股数量限制 ====================

    def _get_position_limit(self, market_trend: Dict[str, Any], base_limit: int = 20) -> int:
        """
        根据大盘趋势调整选股数量
        李成刚：下降趋势时减少选股
        """
        trend = market_trend.get("趋势", "震荡")

        if trend == "上升":
            return base_limit  # 正常数量
        elif trend == "震荡":
            return int(base_limit * 0.6)  # 减少40%
        else:  # 下降
            return int(base_limit * 0.3)  # 减少70%

    def _auto_add_to_observation_pool(self, scored: List[Dict[str, Any]]):
        """
        【v9.0新增】自动将左侧强信号股票加入观察池

        规则：
        - 左侧维度评分 >= 60 分（强左侧信号）
        - 总分 >= 55 分（避免垃圾股）
        - 自动入池，等待次日 T+1~T+3 右侧确认

        Args:
            scored: 已评分的股票列表
        """
        try:
            from observation_tracker import get_observation_tracker
            from datetime import datetime

            tracker = get_observation_tracker()
            today = datetime.now().strftime("%Y-%m-%d")

            added_count = 0
            for stock in scored:
                # 检查左侧维度评分
                left_score = stock.get("左侧", 0)
                total_score = stock.get("总分", 0)

                # 左侧强信号 + 总分达标
                if left_score >= 60 and total_score >= 55:
                    code = stock.get("代码", "")
                    name = stock.get("名称", "")
                    price = stock.get("最新价", 0)
                    signal = f"左侧{left_score}分 | {stock.get('信号', '')}"

                    # 尝试加入观察池
                    success = tracker.add(
                        stock_code=code,
                        stock_name=name,
                        entry_signal=signal,
                        entry_price=price,
                        entry_score=total_score,
                        entry_date=today
                    )

                    if success:
                        added_count += 1
                        logger.info(f"✅ {code} {name} 自动入观察池（左侧{left_score}分）")

            if added_count > 0:
                logger.info(f"本次筛选共 {added_count} 只股票自动入观察池")

        except Exception as e:
            logger.warning(f"自动入观察池失败: {e}")


# 单例
_screener_instance = None

def get_screener(params: Dict[str, Any] = None) -> StockScreener:
    """获取选股器单例"""
    global _screener_instance
    if _screener_instance is None or params:
        _screener_instance = StockScreener(params)
    return _screener_instance
