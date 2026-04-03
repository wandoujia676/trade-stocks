# 小金库 - 智能股票选股验证系统

基于六维度战法的智能选股系统，支持每日自动验证与权重优化。

## 系统架构

```
全市场 5000+ 只股票
       ↓
月度候选池 (100只)  ← monthly_generator.py
       ↓
周选自选股 (20只)   ← screener.py
       ↓
出击股票 (~5只)     ← selection_tracker.py
       ↓
每日验证            ← verifier.py (自动 15:30)
       ↓
权重反馈            ← warfare_config.json
```

## 核心模块

| 模块 | 路径 | 功能 |
|------|------|------|
| **skill_sel** | `stocks/Stock Selection/` | 选股：六维度战法评分 + 三层候选池 |
| **skill_ver** | `stocks/Stock Verification/` | 验证：每日验证出击股票涨跌，自动优化权重 |
| **skill_sell** | `stocks/stock sell/` | 卖出：8种见顶信号 + 分档止盈止损 |

## 技术栈

- **数据源**：Tushare Pro / AKShare / Baostock（自动降级）
- **评分体系**：六维度（趋势/动量/量价/形态/位置/情绪）
- **自动化**：每日 15:30 自动验证（仅在工作日）

## 快速开始

### 1. 安装依赖

```bash
cd stocks
pip install -r requirements.txt
```

### 2. 配置数据源

在 `stocks/Stock Selection/config.py` 中配置 Tushare Token：

```python
TUSHARE_TOKEN = "your_token_here"
```

### 3. 选股

```bash
python stocks/Stock Selection/cli.py
```

或使用 Claude Code 斜杠命令：

```
/stock screener
```

### 4. 每日自动验证

定时任务已配置（每周一到五 15:30）：

```json
{
  "cron": "30 15 * * 1-5",
  "prompt": "执行 verifier.py --auto 进行每日自动验证"
}
```

手动触发：

```bash
python stocks/Stock Verification/verifier.py --auto
```

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 4.1 | 2026-04-03 | 验证改为出击股票；补全股票名称 |
| 4.0 | 2026-04-02 | 止盈止损动态计算；全市场真正筛选 |
| 3.2 | 2026-04-02 | 新增卖出决策系统 skill_sell |
| 3.0 | 2026-04-02 | 修复全市场筛选，加入 Baostock 备选 |
| 2.0 | 2026-04-01 | 三层候选池体系：月→周→出击 |
| 1.0 | 2026-04-01 | 初始版本：选股 + 验证 + 权重优化 |

## 理论依据

系统融合九本股市经典著作的核心方法：

- 《一买即涨》- 均线多头排列
- 《交易真相》- 动量与趋势
- 《量学》- 量价配合分析
- 《短线操盘》- 短期动量信号
- 《股道人生》- 涨停基因识别
- 《股市天经》- K线形态判断

## 注意事项

- 本系统仅供技术研究参考，不构成投资建议
- 股票投资有风险，盈亏自负
- 历史验证成功率不代表未来表现
