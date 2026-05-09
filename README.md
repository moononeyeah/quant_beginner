# quant_beginner

这是一个面向新手的 Python A股/ETF 量化学习项目。项目支持获取行情数据、执行事件驱动回测、参数优化、输出收益结果，并提供 Gradio 可视化页面。

本项目不连接真实交易接口，只用于学习、数据分析和回测练习。
默认 `daily` 使用公开接口的真实历史日线数据；分钟线模式使用公开接口的近期分钟数据，不等同于券商实盘逐笔数据。

## 项目结构

```text
quant_beginner/
├── README.md
├── requirements.txt
├── app.py
├── main.py
├── config.py
├── data/
├── outputs/
├── src/
└── examples/
```

当前版本的 `src/` 已经按可维护的回测结构拆分：

- `src/backtest.py`：回测引擎、成交撮合、逐日盯市、统计汇总
- `src/strategy_base.py`：CTA 模板、Bar 聚合器、ArrayManager、订单和成交基础类型
- `src/strategies/`：策略注册表和 vn.py 风格的预制 CTA 策略
- `src/strategy.py`：兼容层，统一导出策略注册相关接口
- `src/data_fetcher.py`：行情获取和缓存
- `src/plotter.py`：结果画图

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

双均线策略示例：

```bash
python main.py --strategy double_ma --symbol 510300 --frequency daily --start 20230101 --end 20260508
```

也可以修改初始资金和手续费：

```bash
python main.py --strategy double_ma --symbol 000001 --frequency daily --start 20230101 --end 20260508 --cash 100000 --fee 0.0003
```

分钟线示例：

```bash
python main.py --strategy double_ma --symbol 510300 --frequency 5 --start "2026-05-08 09:30:00" --end "2026-05-08 15:00:00"
```

ETF 轮动策略示例：

```bash
python main.py --strategy rotation --symbol 510300 --rotation-symbols 510300,159915,512100,518880,513100 --frequency daily --start 20230101 --end 20260508
```

参数优化示例：

```bash
python main.py --strategy double_ma --symbol 510300 --frequency daily --start 20230101 --end 20260508 --optimize '{"fast_window":[5,10,20],"slow_window":[20,30,60]}'
```

## Gradio 启动方法

```bash
python app.py
```

启动后，终端会显示本地访问地址，通常类似：

```text
http://127.0.0.1:7860
```

在页面中选择策略类型，并输入股票代码或 ETF 池、数据频率、开始时间、结束时间、初始资金和手续费，然后点击“运行回测”。
页面会明确区分历史日线、近期分钟线和 ETF 轮动策略。
页面同时提供：

- 策略参数 JSON
- 优化参数网格 JSON
- 参数优化结果表
- 策略目录、参数定义和源码预览

## 策略说明

### 内置策略

当前内置策略包括：

- `double_ma`
- `atr_rsi`
- `boll_channel`
- `dual_thrust`
- `king_keltner`
- `multi_signal`
- `multi_timeframe`
- `test_strategy`
- `trend_rsi_long`
- `turtle_signal`
- `rotation`

### 双均线策略

双均线策略规则：

- MA5 上穿 MA20：买入
- MA5 下穿 MA20：卖出
- `signal = 1` 表示买入
- `signal = -1` 表示卖出
- `signal = 0` 表示无操作
- `position = 1` 表示持仓
- `position = 0` 表示空仓

### ETF 轮动策略

ETF 轮动策略默认 ETF 池：

- `510300`
- `159915`
- `512100`
- `518880`
- `513100`

轮动规则：

- 仅使用历史日线数据
- 计算每只 ETF 近 20 个交易日涨幅
- 在每个月最后一个交易日对 ETF 池做涨幅排序
- 在下一个交易日开盘调仓到排名第一的 ETF
- 回测输出每次调仓记录，包括调仓日期、目标 ETF、排序结果和组合市值

## 回测逻辑

当前版本的回测内核参考了 `vn.py` 的拆分方式，并把默认策略也迁成了可维护的策略类：

- 初始资金默认 100000
- 策略通过 `StrategyTemplate` 统一管理 `on_init/on_bars/on_trade` 生命周期和目标仓位
- 回测引擎统一处理数据回放、目标仓位调整、开盘成交、逐日盯市和统计计算
- 双均线策略在信号出现后的下一根 K 线开盘成交，而不是在信号当根收盘“穿越成交”
- ETF 轮动策略在调仓日开盘换仓，组合始终单持仓
- 每个交易日都会计算逐日盯市盈亏，包括持仓盈亏、交易盈亏、手续费、净盈亏和账户权益
- 回测统计从日度结果汇总，统一产出收益率、最大回撤、Sharpe、换手和交易天数等指标
- 默认手续费为 0.0003
- 默认滑点为 0
- 仍然不考虑涨跌停无法成交、停牌、分红税费、撮合深度等更真实的交易细节

## 回测指标说明

- 初始资金：回测开始时的本金
- 最终资金：回测结束后的资金
- 总收益率：最终资金相对初始资金的收益比例
- 最大回撤：资金曲线从历史高点到低点的最大跌幅
- 交易次数：完成卖出的交易次数
- 胜率：盈利卖出交易占全部卖出交易的比例
- 资金曲线：每日账户总权益变化
- 日度结果：按天记录交易次数、成交额、手续费、持仓盈亏、交易盈亏和净盈亏

## 数据说明

- `daily`：真实历史日线数据，适合双均线历史回测和 ETF 轮动回测
- `1/5/15/30/60`：近期分钟线数据，适合近实时观察和短周期演示
- 分钟线通常只能获取近期数据，其中 1 分钟数据一般只支持近 5 个交易日
- 以上都属于公开行情接口数据，不代表券商实盘逐笔成交

## 数据缓存与仓库说明

行情数据会缓存到 `data/` 目录。相同代码、频率和时间区间再次运行时，会优先读取本地 CSV 缓存，减少重复请求。
开源仓库默认不提交 `data/`、`outputs/`、`.venv/` 和本地缓存目录。

## 示例脚本

```bash
python examples/demo.py
```

示例脚本默认回测 `510300`。

## 风险提示

本项目仅用于 Python 和量化分析学习，不构成任何投资建议。历史回测结果不代表未来收益，真实交易存在市场风险、流动性风险、交易成本、策略失效等不确定性。请勿直接用于实盘交易。
