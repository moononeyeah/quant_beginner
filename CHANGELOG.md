# Changelog

All notable changes to this project will be documented in this file.

## v0.2.0 - Performance, Optimization & Portfolio Backtesting

### Added

- **Complete performance analytics** (`src/performance.py`):
  - Sharpe ratio, Sortino ratio, Calmar ratio, return/drawdown ratio
  - Trade-level metrics: win rate, profit/loss ratio, avg profit/loss, max profit/loss
  - Time-based metrics: day/week/month win rates
  - Distribution metrics: skewness, kurtosis, VaR(95%), CVaR(95%)
  - Fixed max drawdown duration calculation bug
- **Multi-process parameter optimizer** (`src/optimizer.py`):
  - Parallel grid search with `multiprocessing`
  - Progress callback support
  - Automatic fallback to single-process mode
  - Configurable max workers
- **Portfolio backtesting engine** (`src/portfolio_engine.py`):
  - Multi-symbol simultaneous backtesting with single strategy
  - Equal-weight or custom weight allocation
  - Combined portfolio-level equity curve and statistics
  - Per-symbol result breakdown
- **CLI enhancements** (`main.py`):
  - `--portfolio` / `--portfolio-symbols` for portfolio backtesting
  - `--no-parallel` / `--max-workers` for optimization control
  - Extended output: Sortino, Calmar, profit/loss ratio, day/month win rates

### Changed

- `src/backtest.py`: `calculate_statistics()` now delegates to `performance.calculate_performance()` for richer metrics

## v0.1.0 - Initial open source release

### Added

- Gradio-based visual backtesting workbench.
- CTA-style backtesting engine inspired by vn.py.
- Portfolio-style ETF rotation backtesting path.
- Strategy registry with parameter metadata and source preview support.
- Built-in strategy set:
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
- Local order crossing, stop orders, bar aggregation, daily mark-to-market results, commission, slippage, equity curve, drawdown, Sharpe ratio and win-rate statistics.
- CLI entry for backtesting and parameter optimization.
- Data fetching and cache fallback for A-share and ETF daily/minute bars.
- Matplotlib performance dashboard and signal/equity charts.

### Security and repository hygiene

- Excludes `.venv/`, `data/`, `outputs/`, `.cache/` and Python bytecode from version control.
- Uses GitHub noreply email for commits.
- Publishes source code only; no local market cache, generated charts, credentials or private environment files are included.

### Known limitations

- This is a learning and research project, not a live trading system.
- Public market data interfaces may fail because of network, proxy or upstream API changes.
- Minute data usually covers only recent periods.
- Backtesting does not model limit-up/limit-down failures, suspensions, order book depth, tax, dividends or real brokerage execution constraints.
- The alpha/cross-sectional vn.py demo strategy is not included in this release because it requires a separate alpha engine and signal data model.
