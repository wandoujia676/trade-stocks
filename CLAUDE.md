# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

小金库 (Xiaojinku) is an intelligent stock selection and verification system based on a **pure left-side trading strategy** (纯左侧战法). The core idea: buy at divergence, sell at consensus — identifying stocks before they rally significantly and waiting for rebounds or reversals.

## Architecture

```
三层候选池体系:
全市场 5000+ 股票 → 月度候选池(100只) → 周选自选股(5-20只) → 出击股票(~5只)
    monthly_generator.py      screener.py         selection_tracker.py
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
3. Baostock (last resort)
4. Sina/QQ realtime APIs (for intraday data)

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

### Auto-screening (scheduled tasks)
```bash
python stocks/Stock Selection/auto_screener.py        # weekly (Wed 14:00)
python stocks/Stock Selection/auto_candidate_pool.py # monthly (15th, 28th 14:00)
```

## Pure Left-Side Strategy (纯左侧战法)

Core principle: Buy at divergence, sell at consensus. Identify stocks before significant rallies and wait for rebounds or reversals.

### Seven-Dimension Scoring System (小金库 5.1)

| Dimension | Weight | Left-Side Core Signals |
|-----------|--------|------------------------|
| 左侧 (Left-Side) | 25% | RSI<30, BOLL lower rail<15%, negative deviation |
| 动量 (Momentum) | 15% | MACD green column shrinking, golden cross approaching |
| 量价 (Volume-Price) | 15% | Ground volume bottom, bottom volume expansion |
| 趋势 (Trend) | 25% | MA convergence/accumulation, downtrend收敛 → about to turn up |
| 形态 (Pattern) | 15% | Hammer line, morning star pattern |
| 位置 (Position) | 10% | Low position, near BOLL lower rail |
| 情绪 (Sentiment) | 5% | Limit-up gene, oversold |

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
- `stocks/Stock Selection/data_fetcher.py` - Unified data fetching (Tushare/AKShare/Baostock)
- `stocks/Stock Selection/realtime_fetcher.py` - Real-time quotes (Sina/QQ APIs)
- `stocks/Stock Selection/screener.py` - Pure left-side screening engine
- `stocks/Stock Selection/warfare.py` - Left-side scoring (completely rewritten in 5.1)
- `stocks/Stock Selection/selection_tracker.py` - Generates "出击" stock list
- `stocks/Stock Verification/warfare_config.json` - Dynamic weights after feedback
- `stocks/Stock Selection/View Results/` - Output directory for screener results

## Output Files

```
stocks/Stock Selection/View Results/
├── monthly_watchlist.txt        # Monthly candidate pool (~100 stocks)
├── monthly_candidate_pool.json  # JSON backup
├── weekly_watchlist.txt         # Weekly watchlist (5-20 stocks)
├── weekly_watchlist.json        # JSON backup
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
- 均线死叉, MACD死叉
- 缩量滞涨, 跌破20日均线, 量价背离

## Weight Feedback Loop

The verifier tracks dimension success rates and auto-adjusts weights:
- Success rate >70% → dimension weight +5%
- Success rate <40% → dimension weight -5%
- Per-dimension limits: max 30%, min 15%

## Stop Loss / Take Profit (Left-Side Specific)

- **Stop loss**: 5-12% below recent low (wider than right-side because bottom-fishing)
- **Take profit**: 15-25% target at previous high (larger because mean reversion)
