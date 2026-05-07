# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

小金库 (Xiaojinku) is an intelligent stock selection and verification system based on a **pure left-side trading strategy** (纯左侧战法) with **right-side confirmation** (右侧确认机制, v9.0). The core idea: buy at divergence, sell at consensus — identifying stocks before they rally significantly, then waiting for right-side confirmation before entering positions.

## Architecture

```
三层候选池体系 + 观察池（v9.0新增）:
全市场 5000+ 股票 → 月度候选池(100只) → 周选自选股(5-20只) → 观察池(左侧信号) → 出击股票(~5只)
    monthly_generator.py      screener.py         observation_tracker.py   selection_tracker.py
                                          ↓                    ↓
                                   左侧维度≥60分          T+1~T+3 右侧确认
                                   自动入观察池          (实体阳+量比>1.5)
                                          ↓
                                     每日15:30验证
                                          ↓
                              warfare_config.json (权重反馈)
```

### Core Modules

| Module | Path | Purpose |
|--------|------|---------|
| skill_sel | `stocks/Stock Selection/` | Left-side screening, three-tier candidate pool |
| skill_ver | `stocks/Stock Verification/` | Daily verification + weight optimization |
| skill_sell | `stocks/stock sell/` | 8 sell signals, tiered profit-taking |

### Data Sources (fallback priority)

1. Tushare Pro (primary, requires token in config.py)
2. AKShare (backup)
3. ~~Baostock (disabled in v9.0 due to network blocking issues)~~
4. Sina/QQ realtime APIs (for intraday data)

**Note (v9.0):** Baostock temporarily disabled. Its login process blocks on certain networks. Tushare + AKShare cover all data needs.

## Commands

### Install dependencies
```bash
cd stocks && pip install -r requirements.txt
```

### Run screener (select stocks)
```bash
python stocks/Stock Selection/cli.py screener --market 全市场 --limit 20
python stocks/Stock Selection/cli.py screener --realtime   # intraday mode
python stocks/Stock Selection/cli.py screener --full        # post-market mode (default)
```

### Analyze single stock
```bash
python stocks/Stock Selection/cli.py analyze <stock_code>
```

### Run verification (after market close)
```bash
python stocks/Stock Verification/verifier.py
python stocks/Stock Verification/verifier.py --auto   # only if new picks detected
python stocks/Stock Verification/verifier.py --feedback  # update weights
```

### Sell decision analysis
```bash
python stocks/Stock Selection/cli.py sell 600519@1700 000001@12.5
python stocks/Stock Selection/cli.py sell --test  # demo mode
```

### Monitor commands
```bash
python stocks/Stock Selection/cli.py monitor add <code>
python stocks/Stock Selection/cli.py monitor list
python stocks/Stock Selection/cli.py monitor check
```

### News/Sentiment commands (小金库 6.4)
```bash
python stocks/Stock Selection/cli.py news general              # 市场快讯
python stocks/Stock Selection/cli.py news stock <code>        # 个股新闻
python stocks/Stock Selection/cli.py news sentiment <code>   # 情绪分析
python stocks/Stock Selection/cli.py announcement            # 今日公告
python stocks/Stock Selection/cli.py announcement --symbol <code>  # 个股公告
python stocks/Stock Selection/cli.py limit-up --type up      # 涨停原因追踪
python stocks/Stock Selection/cli.py limit-up --type down    # 跌停原因追踪
```

### Observation Pool commands (小金库 9.0)
```bash
python stocks/Stock Selection/cli.py observation list                   # 列出观察池
python stocks/Stock Selection/cli.py observation list --status pending  # 仅未确认
python stocks/Stock Selection/cli.py observation check                  # 次日检查确认
python stocks/Stock Selection/cli.py observation add <code>             # 手动添加
python stocks/Stock Selection/cli.py observation remove <code>          # 手动移除
```

### Auto-screening (scheduled tasks)
```bash
python stocks/Stock Selection/auto_screener.py        # weekly (Wed 14:00)
python stocks/Stock Selection/auto_candidate_pool.py # monthly (15th, 28th 14:00)
```

### Backtest commands (小金库 9.0)
```bash
# Quick smoke test (5 stocks × 1 month × 1 config, ~5 min)
python run_backtest_v90.py --quick --config baseline

# Full backtest (50 stocks × 2 years × 4 configs, ~1-3 hours)
python run_backtest_v90.py

# Custom date range
python run_backtest_v90.py --start 20240101 --end 20241231

# Single config comparison
python run_backtest_v90.py --config baseline  # v8.x baseline (5 dimensions)
python run_backtest_v90.py --config dim       # Only new dimensions
python run_backtest_v90.py --config obs       # Only observation pool
python run_backtest_v90.py --config v90       # v9.0 full (8 dimensions + obs pool)
```

**Output:**
- `View Results/9.0回测报告.txt` - Human-readable comparison report
- `View Results/9.0回测.json` - Structured results with trade details

**Note:** Fundamentals/MoneyFlow/Catalyst APIs only return latest data. Backtest uses latest data as historical approximation (lookahead bias). Results should be treated as upper-bound reference.

## Pure Left-Side Strategy (纯左侧战法) + Right-Side Confirmation (v9.0)

Core principle: Buy at divergence, sell at consensus. Identify stocks before significant rallies, then wait for right-side confirmation before entering.

### Right-Side Confirmation Mechanism (v9.0)

**Workflow:**
1. Left-side signal triggers (left-side dimension ≥60) → Auto-add to observation pool
2. Wait T+1~T+3 trading days for right-side confirmation
3. Confirmation criteria: **Entity bullish candle (close > open) + Volume ratio > 1.5**
4. Confirmed → Promote to attack pool | Rejected → Exit pool

**Confirmation Window:** T+1 ~ T+3 (3 trading days)
- Any day within window meets criteria → Confirmed
- All 3 days fail → Rejected and exit pool

### Five-Dimension Scoring System (v9.0 - Lagging Indicators Removed)

| Dimension | Weight (v9.0 Step 1) | Weight (v9.0 Step 2) | Core Signals |
|-----------|----------------------|----------------------|--------------|
| 趋势 (Trend) | 22% | **18%** | MA convergence/accumulation, downtrend收敛 → about to turn up |
| 动量 (Momentum) | 25% | **20%** | MACD green column shrinking, golden cross approaching (death cross removed) |
| 左侧 (Left-Side) | 16% | **14%** | RSI<30, BOLL lower rail<15%, negative deviation |
| 量价 (Volume-Price) | 22% | **15%** | Ground volume bottom, bottom volume expansion |
| 形态 (Pattern) | 15% | **8%** | Hammer line, morning star pattern |
| **基本面 (Fundamentals)** | - | **10%** | PE<50 + ROE>8% + 净利润增长率>0% + 资产负债率<70% |
| **资金面 (Money Flow)** | - | **8%** | 主力净流入 + 北向持股变化 + 融资余额变化 |
| **催化剂 (Catalysts)** | - | **7%** | 业绩预告 + 机构调研 + 政策利好 |

**v9.0 Step 1 Changes:**
- ❌ Removed lagging indicators: MACD death cross, green column duration, KDJ death cross
- ✅ Weight rebalancing: Momentum 30%→25%, Trend/Volume-Price 20%→22%, Left-Side 15%→16%
- ✅ Added observation pool for right-side confirmation

**v9.0 Step 2 Changes:**
- ✅ Added 3 new dimensions: Fundamentals (10%), Money Flow (8%), Catalysts (7%)
- ✅ Data sources: Tushare → AKShare → skip (graceful degradation)
- ✅ Cache strategy: Fundamentals 7 days, Money Flow 1 day, Catalysts 3 days
- ✅ Batch prefetch in screener step 3.5 (avoids per-stock API calls during scoring)

### Left-Side Breakout Signals

Stock qualifies as "left-side breakout" when ANY condition is met:
- RSI<25 + BOLL lower rail<15% → Strong signal (+40 points)
- RSI<30 + MA convergence<3% → Medium signal (+30 points)
- Ground volume (volume ratio 0.3-0.5) + price not making new low → Signal (+25 points)
- MACD golden cross approaching + RSI<35 → Signal (+30 points)
- 3 consecutive down days + volume expansion rebound → Signal (+25 points)

### Stock Grading

| Grade | Condition | Position Suggestion |
|-------|-----------|---------------------|
| 主攻 (Main Attack) | Strong left-side signal + score ≥65 | Heavy position |
| 次攻 (Secondary) | Score ≥60 or medium breakout signal | Normal position |
| 观察 (Watch) | Score ≥55 | Light position |
| 备用 (Backup) | Score <55 | Do not participate |

## Key Files

- `stocks/Stock Selection/config.py` - Tushare token and data source config
- `stocks/Stock Selection/data_fetcher.py` - Unified data fetching (Tushare/AKShare) + NewsFetcher (消息面)
- `stocks/Stock Selection/realtime_fetcher.py` - Real-time quotes (Sina/QQ APIs)
- `stocks/Stock Selection/screener.py` - Pure left-side screening engine
- `stocks/Stock Selection/warfare.py` - Left-side scoring (v9.0: 8 dimensions)
- `stocks/Stock Selection/observation_tracker.py` - Observation pool tracker (v9.0 new)
- `stocks/Stock Selection/selection_tracker.py` - Generates "出击" stock list
- `stocks/Stock Selection/backtester.py` - Backtest engine with v9.0 switches (v9.0 new)
- `stocks/Stock Verification/warfare_config.json` - Dynamic weights after feedback
- `stocks/Stock Selection/View Results/` - Output directory for screener results
- `run_backtest_v90.py` - v9.0 backtest comparison script (v9.0 new)

## Output Files

```
stocks/Stock Selection/View Results/
├── monthly_watchlist.txt        # Monthly candidate pool (~100 stocks)
├── monthly_candidate_pool.json  # JSON backup
├── weekly_watchlist.txt         # Weekly watchlist (5-20 stocks)
├── weekly_watchlist.json        # JSON backup
├── 观察池.json                   # Observation pool (v9.0 new)
├── 出击.txt                     # Actionable stocks JSON (~5 stocks)
└── 出击.报告.txt                # Actionable stocks report
```

## Rating System

| Score | Rating | Signal |
|-------|--------|--------|
| ≥80 | A | 强势 (Strong) |
| 65-79 | B+ | 较好 (Good) |
| 55-64 | B | 一般 (Fair) |
| 45-54 | C | 较弱 (Weak) |
| <45 | D | 弱势 (Weakest) |

## Sell Signals (8 types)

From 《一买即涨》《量学》《短线操盘》:
- High-position 十字星, 长上影线, 大阴线
- 缩量滞涨, 跌破20日均线, 量价背离

**Note (v9.0):** Death cross signals (均线死叉, MACD死叉) removed as lagging indicators.

## Weight Feedback Loop

The verifier tracks dimension success rates and auto-adjusts weights:
- Success rate >70% → dimension weight +5%
- Success rate <40% → dimension weight -5%
- Per-dimension limits: max 30%, min 15%

## Stop Loss / Take Profit (Left-Side Specific)

- **Stop loss**: 5-12% below recent low (wider than right-side because bottom-fishing)
- **Take profit**: 15-25% target at previous high (larger because mean reversion)
