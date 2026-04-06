# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

小金库 (Xiaojinku) is an intelligent stock selection and verification system based on a six-dimension trading strategy derived from nine classic stock trading books.

## Architecture

```
三层候选池体系:
全市场 5000+ 股票 → 月度候选池(100只) → 周选自选股(20只) → 出击股票(~5只)
       monthly_generator.py      screener.py        selection_tracker.py
                                          ↓
                                     每日15:30验证
                                          ↓
                              warfare_config.json (权重反馈)
```

### Core Modules

| Module | Path | Purpose |
|--------|------|---------|
| skill_sel | `stocks/Stock Selection/` | Six-dimension scoring, three-tier candidate pool |
| skill_ver | `stocks/Stock Verification/` | Daily verification + weight optimization |
| skill_sell | `stocks/stock sell/` | 8 sell signals, tiered profit-taking |

### Data Sources (fallback priority)

1. Tushare Pro (primary, requires token in config.py)
2. AKShare (backup)
3. Baostock (last resort)

## Commands

### Install dependencies
```bash
cd stocks && pip install -r requirements.txt
```

### Run screener (select stocks)
```bash
python stocks/Stock Selection/cli.py screener --market 全市场 --limit 20
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

## Six-Dimension Scoring System

| Dimension | Weight | Source Books |
|-----------|--------|--------------|
| 趋势 (Trend) | 25% | 《短线操盘》《股道人生》 |
| 动量 (Momentum) | 20% | 《都市》《一买即涨》 |
| 量价 (Volume-Price) | 20% | 《量学》 |
| 形态 (Pattern) | 15% | 《短线操盘》《一买即涨》 |
| 位置 (Position) | 10% | 《一买即涨》 |
| 情绪 (Sentiment) | 10% | 《股道人生》 |

## Key Files

- `stocks/Stock Selection/config.py` - Tushare token and data source config
- `stocks/Stock Selection/data_fetcher.py` - Unified data fetching (Tushare/AKShare/Baostock)
- `stocks/Stock Selection/screener.py` - Six-dimension scoring engine
- `stocks/Stock Selection/warfare.py` - Core scoring weights and calculations
- `stocks/Stock Selection/selection_tracker.py` - Generates "出击" stock list
- `stocks/Stock Verification/warfare_config.json` - Dynamic weights after feedback
- `stocks/Stock Selection/View Results/` - Output directory for screener results

## Rating System

| Score | Rating | Signal |
|-------|--------|--------|
| ≥80 | A | 强势 |
| 65-79 | B+ | 较好 |
| 50-64 | B | 一般 |
| 35-49 | C | 较弱 |
| <35 | D | 弱势 |

## Sell Signals (8 types)

From 《一买即涨》《量学》《短线操盘》:
- High-position十字星, 长上影线, 大阴线
- 均线死叉, MACD死叉
- 缩量滞涨, 跌破20日均线, 量价背离

## Weight Feedback Loop

The verifier tracks dimension success rates and auto-adjusts weights:
- Success rate >70% → dimension weight +5%
- Success rate <40% → dimension weight -5%
- Per-dimension limits: max 30%, min 15%
