# 股票分析报告模板

## 基本信息

| 项目 | 内容 |
|-----|------|
| 股票代码 | {{code}} |
| 股票名称 | {{name}} |
| 分析时间 | {{time}} |
| 最新价格 | {{price}} |
| 涨跌幅 | {{change_pct}} |

## 综合信号

- **信号**：{{signal}}
- **评分**：{{score}}/100
- **理由**：{{reasons}}

## 技术面分析

### 均线系统

| 均线 | 数值 | 价格位置 |
|-----|------|---------|
{{ma_table}}

- 多头排列：{{ma多头排列}}

### MACD

- DIF：{{macd_dif}} | DEA：{{macd_dea}} | MACD柱：{{macd_hist}}
- 位置：{{macd_position}}
- 红柱/绿柱：{{macd_bar}}
- 交叉信号：{{macd_cross}}

### KDJ

- K：{{kdj_k}} | D：{{kdj_d}} | J：{{kdj_j}}
- 信号：{{kdj_signal}}
- 交叉：{{kdj_cross}}

### BOLL

- 上轨：{{boll_upper}} | 中轨：{{boll_mid}} | 下轨：{{boll_lower}}
- 当前位置：{{boll_position}}
- 信号：{{boll_signal}}

### 支撑压力

- 压力位：{{resistance_1}}、{{resistance_2}}
- 支撑位：{{support_1}}、{{support_2}}

### 量价分析

- 信号：{{vol_price_signal}}
- 量比：{{vol_ratio}}

## K线形态

- 识别形态：{{patterns_found}}
{{pattern_signals}}

## 基本面

- 行业：{{industry}}
- 市值：{{market_cap}}
{{fundamental_info}}

## 交易建议

- **建议**：{{suggestion}}
- **止损位**：{{stop_loss}}
- **止盈位**：{{take_profit}}

---

*本报告由Claude Stock Analysis System自动生成，仅供参考，不构成投资建议。*
