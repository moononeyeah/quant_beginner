# quant_beginner

这是一个面向新手的 Python A股/ETF 量化学习项目。项目支持获取行情数据、执行事件驱动回测、参数优化、输出收益结果，并提供 **Streamlit** 可视化页面。

本项目不连接真实交易接口，只用于学习、数据分析和回测练习。
默认 `daily` 使用公开接口的真实历史日线数据；分钟线模式使用公开接口的近期分钟数据，不等同于券商实盘逐笔数据。

## 项目结构

```text
quant_beginner/
├── README.md
├── requirements.txt
├── app.py                  # Streamlit 入口
├── main.py                 # CLI 入口
├── config.py
├── data/                   # 本地缓存
├── outputs/                # 输出图表
├── src/
│   ├── backtest.py         # 回测引擎
│   ├── performance.py      # 完整绩效分析
│   ├── optimizer.py        # 多进程参数优化
│   ├── portfolio_engine.py # 组合回测引擎
│   ├── strategy_base.py    # CTA 模板、Bar 聚合器
│   ├── strategies/         # 策略注册表和预制策略
│   ├── data_fetcher.py     # 行情获取和缓存
│   ├── plotter.py          # 结果画图
│   └── utils.py            # 工具函数
├── pages/                  # Streamlit 多页面
│   ├── 1_单标回测.py
│   ├── 2_组合回测.py
│   ├── 3_参数优化.py
│   ├── 4_策略管理.py
│   └── 5_历史记录.py
└── examples/
```

## 安装方法

建议使用 Python 3.10 或更高版本。

```bash
cd quant_beginner
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果你在 Windows PowerShell 中运行，激活虚拟环境命令通常是：

```powershell
.\.venv\Scripts\Activate.ps1
```

## 命令行运行

### 单标回测

```bash
python main.py --strategy double_ma --symbol 510300 --frequency daily --start 20230101 --end 20260508
```

修改初始资金和手续费：

```bash
python main.py --strategy double_ma --symbol 000001 --frequency daily --start 20230101 --end 20260508 --cash 100000 --fee 0.0003
```

分钟线示例：

```bash
python main.py --strategy double_ma --symbol 510300 --frequency 5 --start "2026-05-08 09:30:00" --end "2026-05-08 15:00:00"
```

### ETF 轮动策略

```bash
python main.py --strategy rotation --symbol 510300 --rotation-symbols 510300,159915,512100,518880,513100 --frequency daily --start 20230101 --end 20260508
```

### 组合回测（多标并行）

```bash
python main.py --portfolio --portfolio-symbols 510300,159915,512100 --strategy double_ma --start 20230101 --end 20260508 --cash 300000
```

### 参数优化

```bash
python main.py --strategy double_ma --symbol 510300 --frequency daily --start 20230101 --end 20260508 --optimize '{"fast_window":[5,10,20],"slow_window":[20,30,60]}'
```

禁用多进程（单线程）：

```bash
python main.py --strategy double_ma --symbol 510300 --frequency daily --start 20230101 --end 20260508 --optimize '{"fast_window":[5,10],"slow_window":[20,30]}' --no-parallel
```

## Streamlit 可视化启动

### 一键启动（推荐）

```bash
./start.sh
```

脚本会自动查找可用端口、启动服务并输出访问地址。

### 手动启动

```bash
streamlit run app.py
```

启动后浏览器自动打开 `http://localhost:8501`。

左侧导航栏包含 5 个功能页面：

| 页面 | 功能 |
|------|------|
| 📊 单标回测 | 选择策略和标的，侧边栏直接编辑参数，查看业绩图表和完整统计指标 |
| 🏗️ 组合回测 | 多标的并行运行同一策略，支持等权或自定义权重分配，汇总子账户绩效 |
| ⚙️ 参数优化 | 设置参数网格，多进程并行扫描，Top-N 结果排序和可视化对比 |
| 📋 策略管理 | 查看所有内置策略的目录、参数定义和源码 |
| 📚 历史记录 | 回测结果自动保存到 SQLite，支持多组对比和删除 |

## 内置策略

当前内置 11 个策略：

| 策略键 | 名称 | 类型 |
|--------|------|------|
| `double_ma` | Double MA（vnpy） | CTA |
| `atr_rsi` | ATR RSI（vnpy） | CTA |
| `boll_channel` | Boll Channel（vnpy） | CTA |
| `dual_thrust` | Dual Thrust（vnpy） | CTA |
| `king_keltner` | King Keltner（vnpy） | CTA |
| `multi_signal` | Multi Signal（vnpy） | CTA |
| `multi_timeframe` | Multi Timeframe（vnpy） | CTA |
| `test_strategy` | Test Strategy（vnpy） | CTA |
| `trend_rsi_long` | Trend RSI Long | CTA |
| `turtle_signal` | Turtle Signal（vnpy） | CTA |
| `rotation` | ETF Rotation | Portfolio |

## 回测指标

### 收益指标
- 总收益率、年化收益率、日收益率

### 风险指标
- 最大回撤、最大回撤百分比、最大回撤持续期
- 年化波动率、日波动率

### 风险调整收益
- **Sharpe 比率** — 单位总风险超额收益
- **Sortino 比率** — 单位下行风险超额收益
- **Calmar 比率** — 年化收益 / 最大回撤
- 收益回撤比

### 交易统计
- 交易次数、胜率、盈亏比
- 平均盈利 / 平均亏损
- 最大单笔盈利 / 最大单笔亏损

### 时间统计
- 总交易日、盈利日数、亏损日数、日胜率
- 盈利周数、亏损周数、周胜率
- 盈利月数、亏损月数、月胜率

### 分布特征
- 偏度、峰度、VaR(95%)、CVaR(95%)

## 回测逻辑

当前版本的回测内核参考了 `vn.py` 的拆分方式：

- 初始资金默认 100000
- 策略通过 `CtaTemplate` 统一管理 `on_init/on_bar/on_trade` 生命周期
- 回测引擎统一处理数据回放、订单撮合、逐日盯市和统计计算
- 支持限价单、停止单、多周期 Bar 聚合
- 每个交易日计算逐日盯市盈亏，包括持仓盈亏、交易盈亏、手续费、滑点、净盈亏和账户权益
- 默认手续费 0.0003，默认滑点 0
- 不考虑涨跌停无法成交、停牌、分红税费、撮合深度等更真实的交易细节

## 数据说明

- `daily`：真实历史日线数据，适合双均线历史回测和 ETF 轮动回测
- `1/5/15/30/60`：近期分钟线数据，适合近实时观察和短周期演示
- 分钟线通常只能获取近期数据，其中 1 分钟数据一般只支持近 5 个交易日
- 以上都属于公开行情接口数据，不代表券商实盘逐笔成交

## 数据缓存

行情数据会缓存到 `data/` 目录。相同代码、频率和时间区间再次运行时，会优先读取本地 CSV 缓存，减少重复请求。
开源仓库默认不提交 `data/`、`outputs/`、`.venv/` 和本地缓存目录。

## 示例脚本

```bash
python examples/demo.py
```

示例脚本默认回测 `510300`。

## 版本历史

参见 [CHANGELOG.md](./CHANGELOG.md)

## 风险提示

本项目仅用于 Python 和量化分析学习，不构成任何投资建议。历史回测结果不代表未来收益，真实交易存在市场风险、流动性风险、交易成本、策略失效等不确定性。请勿直接用于实盘交易。
