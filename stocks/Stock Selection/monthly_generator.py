"""
月度候选股票池生成器
从全市场5000+只股票中初筛100只候选股票

九本书核心理论应用：
- 《短线操盘》《股市扫地僧》- 只做强势股
- 《量学》- 量为价先（量能异常股优先）
- 《一买即涨》- 突破形态（均线/前期高点）
- 《股道人生》- 涨停基因（10日内有涨停记录优先）
- 《交易真相》- 趋势为王

数据获取策略：
- Tushare stock_basic: 获取全市场股票列表（一次API）
- Tushare daily（分批）: 获取近45日日线数据（批量，一次API最多2000条）
"""
import sys
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
import numpy as np

# 添加当前目录
sys.path.insert(0, str(Path(__file__).parent))

from config import TUSHARE_TOKEN, DATA_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 股票代码到名称的映射（用于输出）
STOCK_NAMES = {
    "000001": "平安银行", "600016": "民生银行", "600036": "招商银行",
    "601166": "兴业银行", "601288": "农业银行", "601328": "交通银行",
    "601398": "工商银行", "601818": "光大银行", "600000": "浦发银行",
    "601009": "宁波银行", "601229": "上海银行", "600015": "华夏银行",
    "600030": "中信证券", "600837": "海通证券", "601066": "中信建投",
    "601211": "国泰君安", "601688": "华泰证券", "000776": "广发证券",
    "600109": "国金证券", "601555": "东吴证券", "000712": "锦龙股份",
    "601878": "浙商证券",
    "601318": "中国平安", "601601": "新华保险", "601628": "中国人寿",
    "601336": "新华保险", "601319": "中国人保",
    "000568": "泸州老窖", "000858": "五粮液", "600519": "贵州茅台",
    "603288": "海天味业", "000799": "酒鬼酒", "002304": "洋河股份",
    "600809": "山西汾酒", "000596": "古井贡酒",
    "300750": "宁德时代", "002594": "比亚迪", "600438": "通威股份",
    "601012": "隆基绿能", "002466": "天齐锂业", "600089": "特变电工",
    "600900": "长江电力", "600032": "三花智控", "002459": "晶澳科技",
    "300014": "亿纬锂能",
    "000002": "万科A", "000063": "中兴通讯", "000100": "TCL科技",
    "002230": "科大讯飞", "002241": "歌尔股份", "002415": "海康威视",
    "002460": "赣锋锂业", "300033": "同花顺", "300059": "东方财富",
    "300124": "汇川技术", "000977": "浪潮信息", "600570": "恒生电子",
    "600588": "用友网络", "002410": "广联达",
    "000538": "云南白药", "600276": "恒瑞医药", "603259": "药明康德",
    "300015": "爱尔眼科", "002007": "华兰生物", "000661": "长春高新",
    "300760": "迈瑞医疗", "600196": "复星医药", "300003": "乐普医疗",
    "002371": "北方华创", "688981": "中芯国际", "603501": "韦尔股份",
    "002236": "大华股份", "603986": "兆易创新", "002049": "紫光国微",
    "688008": "澜起科技",
    "000725": "京东方A", "300866": "安克创新", "002475": "立讯精密",
    "300207": "欣旺达", "002351": "漫步者",
    "300059": "东方财富", "300024": "机器人", "300058": "蓝色光标",
    "002027": "分众传媒", "300113": "顺网科技",
    "000002": "万科A", "600048": "保利发展", "600606": "绿地控股",
    "001979": "招商蛇口", "600383": "金地集团", "000671": "阳光城",
    "600309": "万华化学", "600352": "浙江龙盛", "000830": "鲁西化工",
    "002601": "龙佰集团", "600989": "华鲁恒升", "601216": "君正集团",
    "601100": "恒立液压", "002460": "赣锋锂业", "600031": "三一重工",
    "000425": "徐工机械", "002048": "宁波华翔", "300124": "汇川技术",
    "600893": "航发动力", "000768": "中航西飞", "002013": "中航机电",
    "600316": "洪都航空", "601698": "中国卫通", "600760": "中航沈飞",
    "002557": "恰恰食品",
}

# 行业分类（用于分层抽样）
# 注意：这里只作为行业标签备用，不再硬编码为候选池
INDUSTRY_LEADER_CODES = {
    "银行": ["600036", "601398", "601328", "600016", "601166", "000001"],
    "证券": ["600030", "601211", "600837", "601688", "000776"],
    "保险": ["601318", "601628", "601336"],
    "白酒": ["000858", "000568", "600519", "603288"],
    "新能源": ["300750", "002594", "601012", "600438"],
    "医药": ["600276", "603259", "000538", "300760"],
    "科技": ["000063", "002230", "002415", "300059"],
    "芯片": ["002371", "688981", "603501", "688008"],
}

# 全市场筛选模式：不再依赖硬编码龙头
USE_HARDCODED_FALLBACK = False  # 标记是否使用硬编码备选


class MonthlyGenerator:
    """月度候选股票池生成器"""

    def __init__(self):
        self.token = TUSHARE_TOKEN
        self.pro = None
        self._last_call_time = 0
        self._min_interval = 1.2
        self._init_tushare()

    def _init_tushare(self):
        """初始化Tushare"""
        if not self.token:
            logger.warning("未设置Tushare Token，使用模拟数据")
            return
        try:
            import tushare as ts
            ts.set_token(self.token)
            self.pro = ts.pro_api()
            logger.info("Tushare初始化成功")
        except Exception as e:
            logger.error(f"Tushare初始化失败: {e}")
            self.pro = None

    def _rate_limit(self):
        """API频率限制"""
        if not self.pro:
            return
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    def get_all_stocks(self) -> pd.DataFrame:
        """获取全市场股票列表（优先Tushare，失败则用Baostock，最后用hardcoded）"""
        # 先尝试Tushare（带重试）
        if self.pro:
            for attempt in range(3):
                try:
                    self._rate_limit()
                    df = self.pro.stock_basic()
                    if df is not None and not df.empty and isinstance(df, pd.DataFrame):
                        logger.info(f"Tushare获取到 {len(df)} 只股票")
                        return df
                except Exception as e:
                    logger.warning(f"Tushare stock_basic第{attempt+1}次失败: {e}")
                    if attempt < 2:
                        time.sleep(5)  # 等待5秒后重试

        # Baostock备选：获取所有股票列表
        try:
            import baostock as bs
            lg = bs.login()
            if lg.error_code != '0':
                raise Exception(f"Baostock登录失败: {lg.error_msg}")

            rs = bs.query_all_stock(day=datetime.now().strftime("%Y-%m-%d"))
            data = []
            while (rs.error_code == '0') & rs.next():
                data.append(rs.get_row_data())
            bs.logout()

            if data:
                df = pd.DataFrame(data, columns=rs.fields)
                # 正确过滤股票和指数
                # 股票代码规则：
                #   上证: sh.600xxx, sh.601xxx, sh.603xxx, sh.605xxx, sh.688xxx
                #   深证: sz.000xxx(主板), sz.001xxx(主板), sz.300xxx(创业板), sz.002xxx(中小板)
                #   北交所: bj.8xxxxxx
                # 指数代码规则：
                #   上证指数: sh.000xxx, sh.999xxx
                #   深证指数: sz.399xxx

                def is_real_stock(code):
                    """判断是否为真实股票（不是指数）"""
                    code = code.lower()
                    # 上证股票: 600xxx, 601xxx, 603xxx, 605xxx, 688xxx
                    if code.startswith('sh.6'):
                        suffix = code.split('.')[1]
                        # 排除 000xxx, 999xxx（指数）
                        if suffix.startswith('00') or suffix.startswith('99'):
                            return False
                        return True
                    # 深证股票
                    elif code.startswith('sz.0') or code.startswith('sz.3') or code.startswith('sz.002'):
                        # 排除 399xxx（深证指数）
                        suffix = code.split('.')[1]
                        if suffix.startswith('399'):
                            return False
                        return True
                    # 北交所
                    elif code.startswith('bj.8'):
                        return True
                    return False

                df = df[df['code'].apply(is_real_stock)]
                df['symbol'] = df['code'].str.replace(r'^(sh|sz|bj)\.', '', regex=True)
                df['name'] = df['code_name']
                df['industry'] = ''  # Baostock不提供行业信息，留空
                df['list_date'] = '20100101'  # Baostock不提供上市时间，使用默认值
                # 过滤ST股票
                df = df[~df['name'].str.contains('ST', na=False)]
                logger.info(f"Baostock获取到 {len(df)} 只股票")
                return df[['symbol', 'name', 'industry', 'list_date']]
        except Exception as e:
            logger.warning(f"Baostock也失败: {e}，尝试AKShare")

        # AKShare备选：获取所有A股实时数据
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                rename_map = {
                    "代码": "symbol",
                    "名称": "name",
                    "行业": "industry",
                    "上市时间": "list_date",
                }
                df = df.rename(columns=rename_map)
                keep_cols = ["symbol", "name", "industry", "list_date"]
                existing = [c for c in keep_cols if c in df.columns]
                df = df[existing].copy()
                df = df[~df["名称"].str.contains("ST", na=False)]
                logger.info(f"AKShare获取到 {len(df)} 只股票")
                return df
        except Exception as e:
            logger.warning(f"AKShare也失败: {e}，使用hardcoded行业龙头")

        # 最后备选：使用hardcoded行业龙头列表
        logger.info("使用hardcoded行业龙头列表")
        hardcoded = []
        for industry, codes in INDUSTRY_LEADER_CODES.items():
            for code in codes:
                hardcoded.append({
                    "symbol": code,
                    "name": STOCK_NAMES.get(code, code),
                    "industry": industry,
                    "list_date": "20100101",  # 假设都上市超过1年
                })
        return pd.DataFrame(hardcoded)

    def get_daily_batched(self, ts_codes: List[str], days: int = 45) -> pd.DataFrame:
        """
        批量获取日线数据（分批处理）
        ts_codes: 股票代码列表（如 ['000001.SZ', '600036.SH']）
        days: 获取天数
        """
        if not ts_codes:
            return pd.DataFrame()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        all_data = []

        # 如果有 Tushare，优先使用
        if self.pro:
            all_data = self._get_daily_tushare(ts_codes, start_str, end_str)
        else:
            # 否则用 Baostock
            all_data = self._get_daily_baostock(ts_codes, start_str, end_str)

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        # 统一列名
        result = result.rename(columns={"pct_chg": "pct_change", "vol": "volume"})
        # 按日期升序排列
        if "trade_date" in result.columns:
            result = result.sort_values("trade_date").reset_index(drop=True)
        logger.info(f"获取日线数据 {len(result)} 条")
        return result

    def _get_daily_tushare(self, ts_codes: List[str], start_str: str, end_str: str) -> List[pd.DataFrame]:
        """使用 Tushare 批量获取日线"""
        all_data = []
        batch_size = 30

        for i in range(0, len(ts_codes), batch_size):
            batch = ts_codes[i:i+batch_size]
            for ts_code in batch:
                try:
                    self._rate_limit()
                    df = self.pro.daily(
                        ts_code=ts_code,
                        start_date=start_str.replace('-', ''),
                        end_date=end_str.replace('-', '')
                    )
                    if df is not None and not df.empty:
                        all_data.append(df)
                except Exception as e:
                    logger.debug(f"获取 {ts_code} 日线失败: {e}")
                    continue

            if (i + batch_size) % 300 == 0:
                logger.info(f"已处理 {min(i+batch_size, len(ts_codes))}/{len(ts_codes)} 只股票")
        return all_data

    def _get_daily_baostock(self, ts_codes: List[str], start_str: str, end_str: str) -> List[pd.DataFrame]:
        """使用 Baostock 批量获取日线"""
        import baostock as bs

        all_data = []
        lg = bs.login()
        if lg.error_code != '0':
            logger.warning(f"Baostock登录失败: {lg.error_msg}")
            return all_data

        for i, ts_code in enumerate(ts_codes):
            try:
                # Baostock 代码格式: sh.600036 -> 600036
                code = ts_code.replace('.SH', '').replace('.SZ', '').replace('.', '')
                bs_code = f"{'sh' if code.startswith('6') or code.startswith('5') else 'sz'}.{code}"

                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,code,open,high,low,close,volume,pct_change",
                    start_date=start_str,
                    end_date=end_str,
                    frequency="d"
                )

                if rs.error_code == '0':
                    data = []
                    while rs.next():
                        data.append(rs.get_row_data())
                    if data:
                        df = pd.DataFrame(data, columns=['trade_date', 'ts_code', 'open', 'high', 'low', 'close', 'volume', 'pct_change'])
                        all_data.append(df)

            except Exception as e:
                logger.debug(f"获取 {ts_code} 日线失败: {e}")

            if (i + 1) % 100 == 0:
                logger.info(f"Baostock已处理 {i+1}/{len(ts_codes)} 只股票")

        bs.logout()
        return all_data

    def screen(self, target_count: int = 100) -> List[Dict[str, Any]]:
        """
        执行月度候选股票筛选

        Args:
            target_count: 目标选出股票数量，默认100只

        Returns:
            筛选后的股票列表
        """
        logger.info(f"开始月度选股，目标: {target_count} 只")
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 步骤1: 获取全市场股票列表
        all_stocks = self.get_all_stocks()
        if all_stocks.empty:
            logger.error("获取股票列表失败")
            return []

        # 步骤2: 第一轮过滤 - 基本面过滤（5000 -> 约500）
        basic_filtered = self._filter_basic(all_stocks)
        logger.info(f"第一轮基本面过滤后: {len(basic_filtered)} 只")

        if len(basic_filtered) < target_count:
            logger.warning(f"过滤后股票数量({len(basic_filtered)})少于目标({target_count})，扩大候选池")
            # 放宽条件重新过滤
            basic_filtered = self._filter_basic_relaxed(all_stocks)

        # 获取这些股票的日线数据
        ts_codes = [f"{row['symbol']}.{'SZ' if row['symbol'].startswith(('0','3')) else 'SH'}"
                     for _, row in basic_filtered.iterrows()]

        logger.info(f"获取 {len(ts_codes)} 只股票的日线数据...")
        daily_data = self.get_daily_batched(ts_codes, days=45)

        # 步骤3: 第二轮过滤 - 技术面评分（500 -> 100）
        scored = self._score_technical(basic_filtered, daily_data)
        scored.sort(key=lambda x: x["初筛评分"], reverse=True)

        result = scored[:target_count]
        logger.info(f"最终选出 {len(result)} 只股票")

        return result

    def _filter_basic(self, stocks: pd.DataFrame) -> pd.DataFrame:
        """第一轮基本面过滤"""
        if stocks.empty or not isinstance(stocks, pd.DataFrame):
            return pd.DataFrame()

        # 去除ST股票
        stocks = stocks[~stocks["name"].str.contains("ST", na=False)].copy()

        # 如果股票数量很多（>500），使用全市场筛选模式
        if len(stocks) > 500:
            logger.info(f"全市场模式：从{len(stocks)}只股票中筛选")
            return self._filter_full_market(stocks)

        # 否则使用行业龙头模式
        return self._filter_by_industry_leaders(stocks)

    def _filter_full_market(self, stocks: pd.DataFrame) -> pd.DataFrame:
        """从全市场股票中筛选候选股票（5000+ -> ~800）"""
        global USE_HARDCODED_FALLBACK

        # 上市时间过滤（排除上市不足6个月的次新股）
        now = datetime.now()
        six_months_ago = (now - timedelta(days=180)).strftime("%Y%m%d")
        stocks = stocks.copy()

        # 检查是否有有效的list_date
        if "list_date" in stocks.columns and (stocks["list_date"] != '').any():
            stocks["list_date"] = stocks["list_date"].astype(str)
            # 过滤上市超过6个月的股票
            filtered = stocks[stocks["list_date"] < six_months_ago].copy()
            logger.info(f"按上市时间过滤后: {len(filtered)} 只")
        else:
            # 没有上市时间信息，不过滤
            filtered = stocks.copy()
            logger.info(f"无上市时间信息，全量: {len(filtered)} 只")

        # 去除ST股票
        filtered = filtered[~filtered["name"].str.contains("ST", na=False)]
        logger.info(f"去除ST后: {len(filtered)} 只")

        # 如果过滤后数量仍然很多，随机采样到800只（扩大候选池）
        if len(filtered) > 800:
            logger.info(f"全市场筛选：从{len(filtered)}只中随机采样400只")
            # 检查是否有有效的行业信息
            has_valid_industry = (
                "industry" in filtered.columns and
                (filtered["industry"] != '').any() and
                (filtered["industry"].notna()).any()
            )

            if has_valid_industry:
                # 按行业分层采样，每行业最多25只（扩大）
                sampled_list = []
                for industry, group in filtered.groupby("industry"):
                    n = min(len(group), 25)
                    sampled_list.append(group.sample(n=n, random_state=42))
                filtered = pd.concat(sampled_list)
                logger.info(f"按行业分层采样后: {len(filtered)} 只")
            else:
                # 没有行业信息，直接随机采样
                filtered = filtered.sample(n=400, random_state=42)
                logger.info(f"随机采样后: {len(filtered)} 只")

        # 如果最终候选太少（<100），且之前尝试过全市场筛选，标记使用硬编码备选
        if len(filtered) < 100:
            USE_HARDCODED_FALLBACK = True
            logger.warning(f"全市场筛选候选不足{len(filtered)}只，将使用硬编码备选")

        logger.info(f"最终候选股票: {len(filtered)} 只")
        return filtered

    def _filter_by_industry_leaders(self, stocks: pd.DataFrame) -> pd.DataFrame:
        """按行业龙头方式筛选"""
        result = []
        seen_industry = set()

        # 先选各行业龙头（INDUSTRY_LEADER_CODES中的）
        for industry, codes in INDUSTRY_LEADER_CODES.items():
            for code in codes:
                symbol = code.replace(".SH", "").replace(".SZ", "")
                match = stocks[stocks["symbol"] == symbol] if "symbol" in stocks.columns else pd.DataFrame()
                if not match.empty:
                    d = match.iloc[0]
                    result.append(d.to_dict() if hasattr(d, 'to_dict') else dict(d))
                    seen_industry.add(industry)

        # 再从剩余股票中补充，每个行业最多10只
        if "industry" in stocks.columns:
            for industry in stocks["industry"].dropna().unique():
                if industry in seen_industry:
                    continue
                ind_stocks = stocks[stocks["industry"] == industry]
                for _, row in ind_stocks.head(8).iterrows():
                    d = row
                    result.append(d.to_dict() if hasattr(d, 'to_dict') else dict(d))
                seen_industry.add(industry)

        if not result:
            return pd.DataFrame()
        return pd.DataFrame(result)

    def _filter_basic_relaxed(self, stocks: pd.DataFrame) -> pd.DataFrame:
        """放宽条件的基本面过滤（当严格过滤后数量不足时使用）"""
        if stocks.empty:
            return pd.DataFrame()

        # 如果没有list_date列，使用行业龙头模式
        if "list_date" not in stocks.columns or stocks["list_date"].isna().all():
            return self._filter_by_industry_leaders(stocks)

        now = datetime.now()
        one_year_ago = (now - timedelta(days=365)).strftime("%Y%m%d")
        stocks = stocks.copy()
        stocks["list_date"] = stocks["list_date"].astype(str)

        filtered = stocks[
            (~stocks["name"].str.contains("ST", na=False)) &
            (~stocks["name"].str.contains("\\*ST", na=False, regex=True)) &
            (~stocks["name"].str.contains("退", na=False)) &
            (stocks["list_date"] < one_year_ago)
        ]

        # 按行业分类，每行业最多15只
        result = []
        seen_industry = set()

        for industry, codes in INDUSTRY_LEADER_CODES.items():
            for code in codes:
                symbol = code.replace(".SH", "").replace(".SZ", "")
                match = filtered[filtered["symbol"] == symbol]
                if not match.empty:
                    result.append(match.iloc[0].to_dict())

        for industry in stocks["industry"].dropna().unique():
            if industry in seen_industry:
                continue
            ind_stocks = filtered[filtered["industry"] == industry]
            result.extend(ind_stocks.head(12).to_dict("records"))
            seen_industry.add(industry)

        return pd.DataFrame(result) if result else pd.DataFrame()

    def _score_technical(self, stocks: pd.DataFrame, daily_data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        技术面评分 - 优化版

        核心目标：选出高动量股票，而不是稳定型股票
        评分标准来自九本书理论
        """
        results = []

        for _, stock in stocks.iterrows():
            symbol = stock["symbol"]
            # 获取该股票的日线数据
            stock_data = daily_data[daily_data["ts_code"].str.contains(f"{symbol}\\.", regex=True, na=False)]

            if stock_data.empty or len(stock_data) < 20:
                continue

            # 计算技术指标
            close = pd.to_numeric(stock_data["close"], errors="coerce")
            volume = pd.to_numeric(stock_data["volume"], errors="coerce")

            if close.empty or close.iloc[-1] <= 0:
                continue

            # 转换为数值
            close = close.astype(float)
            volume = volume.astype(float)

            # ============ 多周期涨幅计算 ============
            # 5日涨幅（《短线操盘》- 动量）
            if len(close) >= 5:
                change_5d = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100
            else:
                change_5d = 0

            # 10日涨幅
            if len(close) >= 10:
                change_10d = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] * 100
            else:
                change_10d = change_5d * 2

            # 20日涨幅
            if len(close) >= 20:
                change_20d = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100
            else:
                change_20d = change_5d * 4

            # ============ 量能计算 ============
            # 量比（今日量/5日均量）
            vol_5avg = volume[-5:].mean()
            vol_today = volume.iloc[-1]
            vol_ratio = vol_today / vol_5avg if vol_5avg > 0 else 1.0

            # 20日均量对比
            vol_20avg = volume[-20:].mean()
            vol_ratio_20 = vol_today / vol_20avg if vol_20avg > 0 else 1.0

            # ============ 均线系统 ============
            ma5 = close[-5:].mean()
            ma10 = close[-10:].mean()
            ma20 = close[-20:].mean()

            # ============ 高低点计算 ============
            high_20 = close[-20:].max()
            low_20 = close[-20:].min()
            high_50 = close[-50:].max() if len(close) >= 50 else high_20

            latest = close.iloc[-1]

            # ============ 相对位置 ============
            # 距离20日新高百分比
            dist_to_20high = (high_20 - latest) / latest * 100
            # 距离50日新高百分比
            dist_to_50high = (high_50 - latest) / latest * 100

            # ============ 波动率计算（ATR） ============
            # ATR = Average True Range，使用 high, low, previous close 计算
            closes_arr = close.values  # numpy array
            highs_arr = stock_data['high'].astype(float).values
            lows_arr = stock_data['low'].astype(float).values

            true_ranges = []
            for i in range(-1, -min(21, len(closes_arr)), -1):
                idx = len(closes_arr) + i
                if idx > 0 and idx < len(closes_arr):
                    tr = max(
                        highs_arr[idx] - lows_arr[idx],
                        abs(highs_arr[idx] - closes_arr[idx - 1]),
                        abs(lows_arr[idx] - closes_arr[idx - 1])
                    )
                    true_ranges.append(tr)

            atr = np.mean(true_ranges) if true_ranges else latest * 0.02
            atr_pct = atr / latest * 100

            # ============ 涨停基因（《股道人生》）============
            limit_up_count = 0
            limit_up_details = []
            for i in range(1, 11):  # 用正索引
                if i < len(close) and i < len(close):
                    prev_close = float(close.iloc[-i-1]) if -i-1 >= -len(close) else 0
                    curr_close = float(close.iloc[-i])
                    if prev_close > 0:
                        pct = (curr_close - prev_close) / prev_close * 100
                        if pct >= 9.5:
                            limit_up_count += 1
                            limit_up_details.append(f"-{i}日")

            # ============ 评分（《一买即涨》《量学》《交易真相》）============
            score = 0
            reasons = []

            # 1. 高动量评分（核心！30分）- 5日涨幅越大分数越高
            if change_5d >= 20:
                score += 30
                reasons.append(f"强势5日涨{change_5d:.1f}%")
            elif change_5d >= 15:
                score += 25
                reasons.append(f"强劲5日涨{change_5d:.1f}%")
            elif change_5d >= 10:
                score += 20
                reasons.append(f"强势5日涨{change_5d:.1f}%")
            elif change_5d >= 5:
                score += 15
                reasons.append(f"温和5日涨{change_5d:.1f}%")
            elif change_5d >= 0:
                score += 8
            else:
                score += 0  # 下跌股票扣分在下面

            # 2. 下跌股票扣分
            if change_5d < -5:
                score -= 15
            elif change_5d < 0:
                score -= 8

            # 3. 涨停基因（20分）- 来自《股道人生》
            if limit_up_count >= 3:
                score += 20
                reasons.append(f"10日涨停{limit_up_count}次(强)")
            elif limit_up_count == 2:
                score += 15
                reasons.append(f"10日涨停{limit_up_count}次")
            elif limit_up_count == 1:
                score += 10
                reasons.append("10日涨停1次")

            # 4. 突破新高加分（15分）- 来自《一买即涨》
            if dist_to_20high < 2:  # 距离20日新高不到2%
                score += 15
                reasons.append("逼近20日新高")
            elif dist_to_20high < 5:  # 距离20日新高不到5%
                score += 10
                reasons.append("接近20日新高")

            # 5. 量能配合（15分）- 来自《量学》
            if vol_ratio >= 2.0:
                score += 15
                reasons.append(f"放量{vol_ratio:.1f}倍")
            elif vol_ratio >= 1.5:
                score += 10
                reasons.append(f"温和放量{vol_ratio:.1f}倍")
            elif vol_ratio >= 1.2:
                score += 5

            # 6. 均线多头（10分）- 来自《短线操盘》
            if latest > ma5 > ma10 > ma20:
                score += 10
                reasons.append("均线完美多头")
            elif latest > ma5 > ma10:
                score += 7
                reasons.append("均线多头")
            elif latest > ma5:
                score += 3

            # 7. ATR波动率加分（10分）- 高波动股票更有机会
            # 来自《交易真相》- 机会来临时敢于重仓
            if atr_pct >= 4:
                score += 10
                reasons.append(f"高波动(ATR{atr_pct:.1f}%)")
            elif atr_pct >= 2.5:
                score += 5

            # ============ 过滤超大盘股（流通性差的）============
            avg_vol_20 = volume[-20:].mean()
            if avg_vol_20 < 500000:  # 日均成交额太低
                score -= 10

            code_str = str(symbol)
            name = stock.get("name", STOCK_NAMES.get(code_str, ""))
            industry = stock.get("industry", "")

            results.append({
                "code": code_str,
                "name": name,
                "industry": industry,
                "初筛评分": score,
                "评分理由": reasons,
                "最新价": round(latest, 2),
                "5日涨幅": round(change_5d, 2),
                "10日涨幅": round(change_10d, 2),
                "ATR波动": round(atr_pct, 2),
                "量比": round(vol_ratio, 2),
            })

        return results

    def save_result(self, stocks: List[Dict[str, Any]], output_dir: Path):
        """保存结果到文件"""
        output_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. monthly_watchlist.txt（股票代码+名称，用于weekly筛选）
        lines = []
        lines.append("=" * 60)
        lines.append(f"月度候选股票池 - 更新日期: {today}")
        lines.append(f"共 {len(stocks)} 只股票\n")
        for s in stocks:
            industry = s.get("industry", "") or ""
            lines.append(f"{s['code']} - {s['name']} | {industry} | 评分:{s['初筛评分']}")
        watchlist_file = output_dir / "monthly_watchlist.txt"
        with open(watchlist_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        logger.info(f"月度候选池已保存到: {watchlist_file}")

        # 2. monthly_candidate_pool.json（完整数据）
        json_data = {
            "最后更新": today,
            "股票数量": len(stocks),
            "股票列表": stocks
        }
        json_file = output_dir / "monthly_candidate_pool.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        logger.info(f"月度候选池JSON已保存到: {json_file}")

        # 打印摘要
        print(f"\n{'='*60}")
        print(f"月度候选股票池生成完成")
        print(f"{'='*60}")
        print(f"选出: {len(stocks)} 只股票")
        print(f"日期: {today}")
        print(f"\n前20只:")
        for s in stocks[:20]:
            print(f"  {s['code']} {s['name']} | 评分:{s['初筛评分']} | {','.join(s['评分理由'][:2])}")

        return watchlist_file, json_file


def main():
    print("="*60)
    print(f"月度候选股票池生成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    generator = MonthlyGenerator()
    stocks = generator.screen(target_count=100)

    if stocks:
        output_dir = Path(__file__).parent / "View Results"
        generator.save_result(stocks, output_dir)
    else:
        print("\n选股失败，请检查网络和数据源")


if __name__ == "__main__":
    main()
