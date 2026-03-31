# Gamma Scalping 回测策略 - 设计文档

**版本：** v1.0  
**日期：** 2026-03-29  
**状态：** 待用户审阅

---

## 一、项目概述

### 1.1 项目目标
构建 50ETF 期权 Gamma Scalping 量化交易策略的回测系统。

### 1.2 交易标的
- **期权：** 50ETF 期权（510050.XSHG 挂钩的期权合约）
- **Delta 对冲工具：** 50ETF 现货（510050.XSHG）

### 1.3 策略类型
经典 Gamma Scalping（只做多 Gamma）。

---

## 二、使用方法

### 2.1 快速开始

运行回测（使用默认参数）：

```bash
python3 scripts/run_backtest.py
```

查看结果：

```bash
python3 scripts/show_results.py results/latest/
```

### 2.2 常用命令

**自定义数据目录：**
```bash
python3 scripts/run_backtest.py --data ./data
```

**自定义初始资金：**
```bash
python3 scripts/run_backtest.py --capital 2000000
```

**自定义开仓阈值（IV 百分位）：**
```bash
python3 scripts/run_backtest.py --open-threshold 0.20
```

**指定回测日期范围：**
```bash
python3 scripts/run_backtest.py --start 2025-01-01 --end 2025-06-30
```

**指定结果输出目录：**
```bash
python3 scripts/run_backtest.py --results ./results/run1
```

**查看所有可配置参数：**
```bash
python3 scripts/run_backtest.py --list-params
```

**详细输出（显示进度）：**
```bash
python3 scripts/run_backtest.py --verbose
```

### 2.3 结果查看

```bash
# 查看最新结果（交互式选择）
python3 scripts/show_results.py

# 指定结果目录
python3 scripts/show_results.py results/2026-03-29_22-00-20/

# 查看权益曲线
python3 scripts/show_results.py <path> --equity

# 查看交易列表
python3 scripts/show_results.py <path> --trades

# 查看绩效指标
python3 scripts/show_results.py <path> --performance

# 查看配置参数
python3 scripts/show_results.py <path> --config

# 查看全部
python3 scripts/show_results.py <path> --all
```

### 2.4 输出文件

回测完成后，结果保存在 `results/YYYY-MM-DD_HH-MM-SS/` 目录下：

| 文件 | 说明 |
|------|------|
| `summary.csv` | 总绩效统计 |
| `equity_curve.csv` | 每日收益曲线 |
| `equity_curve.png` | 收益曲线图表（权益曲线 + 每日 P&L） |
| `performance.csv` | Greeks P&L 分解 |
| `config.yaml` | 使用的配置参数 |
| `trades/trade_*.csv` | 逐笔交易详情 |
| `underlying_prices.csv` | 每日标的资产价格 |
| `iv_history.csv` | 每日 IV 数据 |

---

## 三、数据规格

### 2.1 数据目录结构

```
data/
├── etf/
│   ├── 510050.XSHG_2024-12-16_price.parquet
│   ├── 510050.XSHG_2024-12-17_price.parquet
│   └── ...
└── options/
    ├── 510050.XSHG_2024-12-16_chain.parquet
    ├── 510050.XSHG_2024-12-17_chain.parquet
    └── ...
```

### 2.2 ETF 现货数据格式

**文件：** `etf/*_price.parquet`  
**字段：**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| date | Index | 日期 |
| open | float64 | 开盘价（元） |
| close | float64 | 收盘价（元） |
| high | float64 | 最高价（元） |
| low | float64 | 最低价（元） |
| volume | float64 | 成交量 |
| money | float64 | 成交额（元） |

### 2.3 期权链数据格式

**文件：** `options/*_chain.parquet`  
**字段：**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| order_book_id | object | 期权代码 |
| strike_price | float64 | 行权价（元） |
| maturity_date | object | 到期日（YYYY-MM-DD） |
| option_type | object | C（认购）/ P（认沽） |
| bid | float64 | 买一价（元） |
| ask | float64 | 卖一价（元） |
| volume | int64 | 成交量 |
| open_interest | int64 | 持仓量 |
| contract_multiplier | int64 | 合约乘数（10000） |
| close | float64 | 收盘价（元） |

### 2.4 Greeks 计算参数

| 参数 | 值 |
|------|-----|
| 无风险利率 | 2.5% 年化 |
| 期权价格 | (bid + ask) / 2 |
| 标的价格 | ETF 现货 close |

### 2.5 数据时间范围
- 起始：2024-12-16
- 结束：2025-12-23
- 交易日数量：253 天

---

## 四、波动率锥构建

### 4.1 目标
构建不同剩余期限的 IV 历史分位数曲线，用于判断当前 IV 的历史相对位置。

### 4.2 回望窗口

**参数：** `lookback_days = 120`

对于每个交易日 T，构建波动率锥时只使用 T 之前 **120 个交易日**的历史 IV 数据。

- 若 T 之前的历史数据**少于 60 个交易日**，则跳过 T，当日**不进行开仓检查**
- 该窗口按交易日计算，最多取 120 个交易日，至少需要 60 个交易日方可构建波动率锥

### 4.3 ATM 期权筛选规则
1. 使用 **Call + Put 配对**筛选：同一行权价、同一到期日的 Call 和 Put 组成期权对
2. ATM = 行权价**最接近**当日 ETF 现货收盘价
3. 剔除条件（任一满足则忽略该期权对）：
   - Call IV = 0 或 Put IV = 0（计算失败）
   - abs(Call IV - Put IV) > 阈值（默认 15%，可配置 `max_call_put_iv_diff`）
   - 剩余到期天数 < min_dte（可配置，默认 4 天）
   - 期权价格 < 0.001 元（异常值）

### 4.4 IV 计算
使用 Black-Scholes 模型反推隐含波动率。

**输入：** S（标的价格）、K（行权价）、r（无风险利率）、T（剩余到期时间年化）、option_price（(bid+ask)/2）

**输出：** 年化 IV（如 0.18 表示 18%）

**波动率锥 IV 取值：** Call 和 Put IV 的**平均值**（过滤后的期权对）

**过滤逻辑：** 若 Call/Put IV 差值超过 `max_call_put_iv_diff`（默认 15%），该期权对不参与计算

### 4.5 期限分组

| 目标窗口 | 剩余天数范围 |
|---------|-------------|
| 7 天 | 5 - 9 天 |
| 14 天 | 10 - 18 天 |
| 30 天 | 22 - 37 天 |
| 60 天 | 45 - 75 天 |
| 90 天 | 75 - 105 天 |

### 4.6 分位数计算
每个期限窗口计算 11 个分位数：最大值、90%、85%、80%、75%、50%、25%、20%、15%、10%、最小值。

---

## 五、策略开平仓逻辑

### 5.1 开仓条件（同时满足）
1. 目标期限的 IV 百分位 **< 低阈值**（默认 15%，可配置）
2. 可用资金 > 0
3. **流动性检查：** Call 和 Put 的成交量均 > 2000

### 5.2 开仓操作
找到满足 moneyness 条件的 ATM 期权对：
- **Moneyness 范围：** ETF 现货价格 × [0.95, 1.05]
- **跨式组合：** 买入 1 张 Call + 1 张 Put（同一行权价）
- **行权价选择：** moneyness 范围内最接近 ATM 的行权价

### 5.3 平仓条件（满足任一即平仓）
1. IV 百分位 **> 高阈值**（默认 85%，可配置）
2. 剩余到期天数 **≤ 5 天**
3. 持仓天数 **> 30 天**（从开仓日起算）

### 5.4 Delta 对冲规则
- **触发条件：** 持仓 delta 绝对值 > 0.05
- **对冲操作：** 买卖 ETF 现货使 delta 归零
- **特殊规则：** 开仓日，平仓日**不进行** delta 对冲

### 5.5 每日操作顺序
```
1. 检查能否开仓 → 能则开仓，当日结束
2. 检查能否平仓 → 能则平仓，当日结束
3. 检查 delta 对冲需求 → 执行对冲
```

---

## 六、交易成本

### 6.1 期权交易成本

| 费用类型 | 计算方式 |
|---------|---------|
| 佣金 | 成交金额 × 0.03%（最低 5 元/笔） |
| 经手费 | 成交金额 × 0.001% |
| 过户费 | 成交金额 × 0.001%（仅上海证券交易所） |
| 印花税 | 无（期权不征印花税） |
| 滑点 | 买入时 ask 额外 +0.5%，卖出时 bid 额外 -0.5% |

**买入成本：** (ask_price × 1.005) × contract_multiplier × 张数 + 佣金 + 经手费 + 过户费  
**卖出收入：** (bid_price × 0.995) × contract_multiplier × 张数 - 佣金 - 经手费 - 过户费

### 6.2 ETF 现货交易成本

| 费用类型 | 计算方式 |
|---------|---------|
| 佣金 | 成交金额 × 0.05%（最低 5 元/笔） |
| 经手费 | 成交金额 × 0.001% |
| 印花税 | 成交金额 × 0.05%（仅卖出时征收） |
| 滑点 | 买入时额外 +0.1%，卖出时额外 -0.1% |

**买入成本：** close_price × 1.001 × (1 + 0.1%) × 份额  
**卖出收入：** close_price × 0.999 × (1 - 0.1%) × 份额

---

## 七、仓位管理

### 7.1 仓位记录单位
以 **trade_id** 为唯一标识，管理一笔跨式仓位的完整生命周期。

### 7.2 同一行权价限制
同一行权价的跨式组合，**同时最多持有 1 组**。

### 5.3 资金管理
- 初始资金：1,000,000 元
- 可用资金 > 0 即可开仓
- 无仓位上限（风险自控）

### 5.4 Delta 对冲累计逻辑
- 对冲操作**累加计算**净持仓
- 示例：卖出 4000 份 → 买入 1000 份 → 当前净卖出 3000 份
- 每次对冲记录累计净仓位

### 5.5 仓位记录内容

**trade_id 记录包含：**

| 阶段 | 记录内容 |
|------|---------|
| 开仓 | 开仓日期、期权代码、行权价、到期日、开仓价格、权利金支出 |
| 持仓 | 每日持仓 delta、gamma、vega、theta（金额口径） |
| 对冲 | 每次对冲日期、对冲数量（ETF）、累计净持仓 |
| 平仓 | 平仓日期、平仓价格、权利金收入、总损益 |

---

## 九、回测输出结构

### 9.1 输出根目录
```
results/{timestamp}/
```
时间戳格式：`YYYY-MM-DD_HH-MM-SS`

### 9.2 目录结构

```
results/{timestamp}/
├── config.yaml              # 回测配置参数
├── trades/                  # 逐笔交易详情
│   ├── trade_001.csv
│   ├── trade_002.csv
│   └── ...
├── summary.csv              # 总绩效统计
├── equity_curve.csv         # 每日收益曲线
├── performance.csv          # Greeks 收益分解表
└── logs/
    └── daily_debug.log     # 每日调试信息
```

### 9.3 总绩效统计（summary.csv）

| 指标 | 说明 |
|------|------|
| 总交易次数 | 完整开平仓的交易笔数 |
| 盈利交易次数 | 盈利的 trade 数量 |
| 亏损交易次数 | 亏损的 trade 数量 |
| 总权利金收支 | 所有开平仓权利金净收入 |
| 总对冲损益 | 所有对冲操作的累计盈亏 |
| 总实际损益 | 总 P&L |
| 胜率 | 盈利交易 / 总交易 |
| 平均盈利 | 盈利交易的平均收益 |
| 平均亏损 | 亏损交易的平均亏损 |

### 9.4 每日收益曲线（equity_curve.csv）

| 字段 | 说明 |
|------|------|
| date | 日期 |
| equity | 当日账户总权益 |
| daily_pnl | 当日损益 |
| cumulative_pnl | 累计损益 |

### 9.5 Greeks 收益分解（performance.csv）

**分解公式（梯形积分）：**

| 组分 | 公式 |
|------|------|
| Delta P&L | (Δ_i + Δ_{i+1}) / 2 × ΔS_i |
| Gamma P&L | 1/4 × (Γ_i + Γ_{i+1}) × (ΔS_i)² |
| Theta P&L | (Θ_i + Θ_{i+1}) / 2 × Δt_i |
| Vega P&L | (Vega_i + Vega_{i+1}) / 2 × Δσ_i |

**总理论 P&L = Σ(Delta + Gamma + Theta + Vega)**

### 9.6 误差验证
- Greeks 分解 P&L 与实际 P&L 误差需 < 5%
- 误差 = 实际 P&L - 理论 P&L

### 9.7 收益曲线可视化
- 回测引擎在每次运行后生成 `equity_curve.png` 到 results 目录
- 图表为 2-panel 结构：
  - 上半部分：权益曲线（Equity Curve），展示账户权益随时间的变化
  - 下半部分：每日 P&L 条形图（Daily P&L Bar Chart），绿色表示正收益，红色表示负收益
- X 轴显示日期，Y 轴分别显示权益值和每日 P&L
- 输出文件：`results/{timestamp}/equity_curve.png`

---

## 十、调试信息

### 10.1 每日调试日志（daily_debug.log）

每日输出以下信息：

```
=== 2024-12-20 ===
[ATM Candidates]
Strike=2.650, Type=C, IV=0.1823, Percentile=12.5%
Strike=2.650, Type=P, IV=0.1821, Percentile=12.3%

[IV Percentile by Tenor]
7d:  8.2% (Open threshold: 15%)
14d: 11.5%
30d: 12.5% <-- Target tenor
60d: 18.3%
90d: 22.1%

[Positions]
trade_id=001, strike=2.650, maturity=2025-01-22, delta=0.23, gamma=1234.5, vega=567.8, theta=-89.2
Action: No hedge needed (|delta|=0.23 < 0.05)
```

---

## 八、代码架构

### 8.1 模块划分

```
gamma_scalping/
├── __init__.py
├── config.py              # 配置管理
├── data/                   # 数据层
│   ├── __init__.py
│   ├── base.py             # 数据源抽象基类
│   ├── local.py            # 本地 parquet 数据源
│   └── interface.py        # 统一数据接口
├── core/                   # 核心策略
│   ├── __init__.py
│   ├── greeks.py           # Greeks 计算（BS 模型）
│   ├── vol_cone.py         # 波动率锥构建
│   ├── signal.py           # 开平仓信号
│   └── hedge.py            # Delta 对冲逻辑
├── portfolio/              # 仓位管理
│   ├── __init__.py
│   ├── position.py         # 单笔仓位
│   └── portfolio.py        # 账户组合
├── backtest/               # 回测引擎
│   ├── __init__.py
│   ├── engine.py           # 回测主循环
│   └── processor.py        # 逐日处理器
├── analysis/               # 收益分析
│   ├── __init__.py
│   ├── performance.py      # 绩效统计
│   ├── greeks_pnl.py       # Greeks P&L 分解
│   └── visualization.py    # 可视化
└── utils/                  # 工具
    ├── __init__.py
    ├── date.py             # 日期工具
    └── math.py             # 数学工具
```

### 8.2 数据源解耦

**基类 `DataSourceBase`：**

```python
class DataSourceBase(ABC):
    @abstractmethod
    def get_etf_price(self, date: str) -> pd.DataFrame: ...
    
    @abstractmethod
    def get_options_chain(self, date: str) -> pd.DataFrame: ...
    
    @abstractmethod
    def get_date_range(self) -> tuple[str, str]: ...
```

**本地实现 `LocalDataSource`：**

```python
class LocalDataSource(DataSourceBase):
    def __init__(self, data_dir: str): ...
    # 实现各抽象方法
```

**扩展方式：** 实现新的 `DataSourceBase` 子类即可接入其他数据源（如 API、数据库）。

---

## 十一、配置参数

### 11.1 可配置参数

| 参数 | 默认值 | 说明 |
|------|-------|------|
| initial_capital | 1,000,000 | 初始资金（元） |
| lookback_days | 120 | 波动率锥回望窗口（交易日） |
| open_threshold | 0.15 | 开仓 IV 百分位阈值 |
| close_threshold | 0.85 | 平仓 IV 百分位阈值 |
| close_dte_threshold | 5 | 平仓剩余到期天数阈值 |
| max_holding_days | 30 | 最大持仓天数阈值 |
| delta_hedge_threshold | 0.05 | Delta 对冲阈值 |
| moneyness_range | [0.95, 1.05] | Moneyness 范围 |
| target_tenor | 30 | 目标期限（天） |
| min_dte | 7 | 最小剩余到期天数 |
| min_option_price | 0.001 | 期权最低价格（元） |
| min_volume | 2000 | 开仓流动性阈值（成交量） |
| risk_free_rate | 0.025 | 无风险利率 |
| option_commission | 0.0003 | 期权佣金率（0.03%） |
| option_min_commission | 5 | 期权最低佣金（元/笔） |
| option_handling_fee | 0.00001 | 期权经手费率（0.001%） |
| option_transfer_fee | 0.00001 | 期权过户费率（0.001%） |
| option_slippage | 0.005 | 期权滑点（0.5%） |
| etf_commission | 0.0005 | ETF 佣金率（0.05%） |
| etf_min_commission | 5 | ETF 最低佣金（元/笔） |
| etf_handling_fee | 0.00001 | ETF 经手费率（0.001%） |
| etf_stamp_tax | 0.0005 | ETF 印花税率（0.05%，仅卖出） |
| etf_slippage | 0.001 | ETF 滑点（0.1%） |

---

## 十二、参数优化模块

### 12.1 优化参数列表

以下参数设计为可优化参数，供参数扫描和寻优使用：

| 类别 | 参数 | 建议扫描范围 | 步长 |
|------|------|-------------|------|
| 波动率锥 | lookback_days | 60 - 240 | 30 |
| 波动率锥 | target_tenor | 14, 30, 60, 90 | - |
| 开仓信号 | open_threshold | 0.05 - 0.30 | 0.05 |
| 平仓信号 | close_threshold | 0.70 - 0.95 | 0.05 |
| 平仓信号 | close_dte_threshold | 3 - 10 | 1 |
| 平仓信号 | max_holding_days | 15 - 45 | 5 |
| 对冲信号 | delta_hedge_threshold | 0.02 - 0.10 | 0.02 |
| 流动性 | min_volume | 1000 - 5000 | 1000 |
| ATM 范围 | moneyness_range | [0.93, 1.07] 等 | - |

### 12.2 优化目标

| 指标 | 说明 |
|------|------|
| 总收益率 | (期末权益 - 期初权益) / 期初权益 |
| 夏普比率 | 年化收益 / 年化波动率 |
| 最大回撤 | 权益曲线最大回撤比例 |
| 胜率 | 盈利交易数 / 总交易数 |
| 卡尔马比率 | 年化收益率 / 最大回撤 |

### 12.3 优化输出

```
results/optimization/
├── grid_search_results.csv    # 全量参数扫描结果
├── best_params.yaml           # 最优参数组合
└── equity_curves/             # 各参数组合的权益曲线
```

---

## 十三、开发计划

### 模块开发顺序

1. **数据层** — `data/` 模块
2. **Greeks 计算** — `core/greeks.py`
3. **波动率锥** — `core/vol_cone.py`
4. **仓位管理** — `portfolio/` 模块
5. **信号与对冲** — `core/signal.py`, `core/hedge.py`
6. **回测引擎** — `backtest/` 模块
7. **收益分析** — `analysis/` 模块
8. **可视化** — `analysis/visualization.py`

---

## 十四、待补充

- （暂无）

---

## 十五、审阅记录

| 版本 | 日期 | 审阅状态 |
|------|------|---------|
| v1.0 | 2026-03-29 | 待审阅 |
