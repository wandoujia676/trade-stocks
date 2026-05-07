# 小金库 9.0 版本说明

**发布日期**: 2026-05-07  
**核心改进**: 观察池右侧确认 + 8 维度评分体系 + 回测验证框架

---

## 三大核心改进

### 1. 观察池 + 右侧确认机制（Step 1）

**问题**：v8.x 纯左侧战法容易「抄底抄在半山腰」，左侧信号触发后立即买入风险高。

**解决方案**：
- 左侧信号触发（左侧维度≥60）→ 自动进入**观察池**
- 等待 T+1 ~ T+3 交易日的**右侧确认**
- 确认条件：**实体阳线（close > open）+ 量比 > 1.5**
- 确认通过 → 晋级出击池 | 3 日内未确认 → 退出观察池

**效果**：
- ✅ 降低「抄底失败」风险
- ✅ 提高买入时机精准度
- ✅ 保留左侧战法的「提前布局」优势

**新增命令**：
```bash
python stocks/Stock Selection/cli.py observation list
python stocks/Stock Selection/cli.py observation check
```

**新增文件**：
- `stocks/Stock Selection/observation_tracker.py`
- `stocks/Stock Selection/View Results/观察池.json`

---

### 2. 8 维度评分体系（Step 2）

**问题**：v8.x 只有 5 个技术维度（趋势/动量/左侧/量价/形态），缺少基本面和资金面判断。

**解决方案**：新增 3 个维度，从 5 维 → 8 维

| 新维度 | 权重 | 核心指标 | 数据源 |
|--------|------|----------|--------|
| **基本面** | 10% | PE<50 + ROE>8% + 净利润增长率>0% + 资产负债率<70% | Tushare → AKShare |
| **资金面** | 8% | 主力净流入 + 北向持股变化 + 融资余额变化 | Tushare → AKShare |
| **催化剂** | 7% | 业绩预告 + 机构调研 + 政策利好 | Tushare → AKShare |

**权重调整**（为新维度腾出空间）：
- 趋势：22% → 18%
- 动量：25% → 20%
- 左侧：16% → 14%
- 量价：22% → 15%
- 形态：15% → 8%

**缓存策略**（避免频繁 API 调用）：
- 基本面：7 天
- 资金面：1 天
- 催化剂：3 天

**批量预取**（screener step 3.5）：
- 在筛选阶段一次性拉取所有候选股票的新维度数据
- 避免评分阶段逐只股票调用 API（从 100 次 → 1 次）

**效果**：
- ✅ 过滤「技术面好看但基本面烂」的垃圾股
- ✅ 捕捉「主力资金流入 + 机构调研」的强势股
- ✅ 识别「业绩预告利好 + 政策催化」的潜力股

---

### 3. 回测验证框架（Step 3）

**问题**：v8.x 没有回测工具，无法量化验证策略改进效果。

**解决方案**：
- 新建 `backtester.py`：支持 v9.0 两个开关（`use_v90_dimensions` / `use_observation_pool`）
- 新建 `run_backtest_v90.py`：4 种组合对比脚本
  - (False, False) = v8.x 基线（5 维度，无右侧确认）
  - (True, False) = 仅加新维度（8 维度）
  - (False, True) = 仅加观察池（5 维度 + 右侧确认）
  - (True, True) = v9.0 完整版（8 维度 + 右侧确认）

**回测参数**：
- 股票池：50 只沪深 300 权重股（覆盖大盘 + 多行业）
- 默认区间：2024-05-07 ~ 2026-05-07（近 2 年）
- 止损/止盈：8% / 20%
- 单次仓位：10%
- 初始资金：100 万

**输出**：
- `View Results/9.0回测报告.txt`（人类可读对比表）
- `View Results/9.0回测.json`（结构化结果 + 交易明细）

**快速验证**：
```bash
python run_backtest_v90.py --quick --config baseline  # 5 只 × 1 月，~5 分钟
```

**完整回测**：
```bash
python run_backtest_v90.py  # 50 只 × 2 年 × 4 配置，~1-3 小时
```

**已知限制**：
- ⚠️ 基本面/资金面/催化剂接口仅返回最新数据，回测中用最新数据近似历史（lookahead bias）
- ⚠️ 结果应作为「上限参考」而非真实表现
- ⚠️ 报告中已明确标注此限制

---

## 其他改进

### 数据源优化
- **禁用 Baostock**：其 `bs.login()` 在某些网络环境会阻塞几十分钟，导致初始化卡死
- **按需初始化**：`UnifiedDataFetcher` 只创建 `DATA_SOURCE_PRIORITY` 列表中的数据源
- **Tushare + AKShare 已覆盖所有需求**

### 进度日志增强
- `run_backtest_v90.py`：stdout 行缓冲 + 配置开始/结束时间戳
- `backtester.run()`：每个月打印进度 `[X/Y]`，选股数量、右侧确认过滤数量
- 实时刷新（`flush=True`），避免用户误以为脚本卡住

### Bug 修复
- ✅ `--quick` 模式现在尊重 `--config` 参数
- ✅ `_calculate_stats` 在 trades 为空时返回完整字段，避免 KeyError
- ✅ 观察池晋级逻辑的字段映射完整性验证

---

## 升级指南

### 从 v8.x 升级到 v9.0

**1. 拉取最新代码**
```bash
git pull origin main
git checkout v9.0
```

**2. 无需修改配置**
- `config.py` 中的 `DATA_SOURCE_PRIORITY` 已自动调整
- Tushare token 保持不变

**3. 新增依赖（如果之前没装）**
```bash
cd stocks && pip install -r requirements.txt
```

**4. 验证安装**
```bash
# 查看观察池（应该为空或有历史数据）
python stocks/Stock Selection/cli.py observation list

# 跑快速回测验证
python run_backtest_v90.py --quick --config baseline
```

**5. 日常使用**
- 选股流程**完全不变**：`cli.py screener` 自动使用 8 维度 + 观察池
- 次日盘后执行：`cli.py observation check` 检查右侧确认
- 出击股票在 `View Results/出击.txt` 和 `View Results/出击.报告.txt`

---

## 已知限制与未来计划

### 当前限制
1. **回测数据 lookahead bias**：基本面/资金面/催化剂接口只能拿最新数据，回测结果是上限参考
2. **观察池容量无上限**：理论上可能积累大量未确认股票（实际使用中不太可能）
3. **右侧确认窗口固定 3 天**：未来可考虑根据市场环境动态调整

### 未来计划（v9.1+）
- [ ] 基本面/资金面历史数据接口适配（如果 Tushare 提供）
- [ ] 观察池容量上限 + LRU 淘汰策略
- [ ] 右侧确认窗口自适应（牛市缩短 / 熊市延长）
- [ ] 回测框架支持多策略对比（左侧 vs 波段 vs 混合）
- [ ] Web 可视化界面（观察池状态 + 回测曲线）

---

## 贡献者

- **核心开发**: wandoujia186
- **AI 辅助**: Claude (Anthropic)

---

## 许可证

本项目仅供学习交流使用，不构成投资建议。股市有风险，投资需谨慎。
