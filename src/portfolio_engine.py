from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.backtest import BacktestResult, CtaBacktestingEngine
from src.performance import PerformanceMetrics, calculate_performance
from src.strategy_base import TradeRecord
from src.strategies import get_strategy_spec


@dataclass
class PortfolioBacktestResult:
    """组合回测结果。"""

    initial_cash: float = 0.0
    final_cash: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0

    equity_curve: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    trades: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    daily_results: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    statistics: dict[str, Any] = field(default_factory=dict)
    per_symbol_results: dict[str, BacktestResult] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    @property
    def metrics(self) -> PerformanceMetrics | None:
        if self.daily_results.empty:
            return None
        return calculate_performance(
            daily_df=self.daily_results,
            trades_df=self.trades,
            capital=self.initial_cash,
        )


def _allocate_capital(
    symbols: list[str],
    total_capital: float,
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """按权重分配资金，默认等权。"""
    if weights:
        total_weight = sum(weights.get(s, 0.0) for s in symbols)
        if total_weight <= 0:
            raise ValueError("权重总和必须大于 0")
        return {
            s: total_capital * (weights.get(s, 0.0) / total_weight)
            for s in symbols
        }
    n = len(symbols)
    return {s: total_capital / n for s in symbols}


def _merge_daily_results(
    per_symbol_results: dict[str, BacktestResult],
    initial_cash: float,
) -> pd.DataFrame:
    """合并各子账户的日度结果为组合日度结果。"""
    all_dates: set[pd.Timestamp] = set()
    symbol_dfs: dict[str, pd.DataFrame] = {}

    for symbol, result in per_symbol_results.items():
        df = result.daily_results.copy()
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["date"])
        symbol_dfs[symbol] = df
        all_dates.update(df["date"].tolist())

    if not all_dates:
        return pd.DataFrame(columns=["date", "equity", "net_pnl", "trade_count", "turnover", "commission"])

    dates = sorted(all_dates)
    rows: list[dict[str, Any]] = []
    for date in dates:
        total_net_pnl = 0.0
        total_turnover = 0.0
        total_commission = 0.0
        total_slippage = 0.0
        total_trade_count = 0
        for symbol, df in symbol_dfs.items():
            row = df[df["date"] == date]
            if row.empty:
                continue
            r = row.iloc[0]
            total_net_pnl += float(r.get("net_pnl", 0.0))
            total_turnover += float(r.get("turnover", 0.0))
            total_commission += float(r.get("commission", 0.0))
            total_slippage += float(r.get("slippage", 0.0))
            total_trade_count += int(r.get("trade_count", 0))
        rows.append(
            {
                "date": date,
                "net_pnl": total_net_pnl,
                "turnover": total_turnover,
                "commission": total_commission,
                "slippage": total_slippage,
                "trade_count": total_trade_count,
            }
        )

    merged = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    merged["equity"] = merged["net_pnl"].cumsum() + initial_cash
    return merged


def _merge_trades(per_symbol_results: dict[str, BacktestResult]) -> pd.DataFrame:
    """合并各子账户的成交记录。"""
    all_trades: list[dict[str, Any]] = []
    for symbol, result in per_symbol_results.items():
        df = result.trades.copy()
        if df.empty:
            continue
        df["portfolio_symbol"] = symbol
        all_trades.append(df)
    if not all_trades:
        return pd.DataFrame()
    return pd.concat(all_trades, ignore_index=True)


def _merge_logs(per_symbol_results: dict[str, BacktestResult]) -> list[str]:
    logs: list[str] = []
    for symbol, result in per_symbol_results.items():
        logs.extend([f"[{symbol}] {log}" for log in result.logs])
    return logs


class PortfolioBacktestEngine:
    """
    多标组合回测引擎。

    每个标的上运行一个独立的 CTA 策略实例，按权重分配子资金。
    最后合并日度结果、成交记录和日志，生成组合级绩效。
    """

    def __init__(
        self,
        data: pd.DataFrame,
        strategy_class: type,
        strategy_setting: dict[str, Any] | None = None,
        symbols: list[str] | None = None,
        weights: dict[str, float] | None = None,
        rate: float = 0.0003,
        slippage: float = 0.0,
        size: float = 1.0,
        pricetick: float = 0.01,
        capital: float = 100000.0,
    ) -> None:
        if data.empty:
            raise ValueError("无法回测：数据为空")

        data = data.copy()
        data["date"] = pd.to_datetime(data["date"])
        if "symbol" not in data.columns:
            data["symbol"] = "DEFAULT"

        self.symbols = symbols or data["symbol"].astype(str).unique().tolist()
        if not self.symbols:
            raise ValueError("没有可回测的标的")

        self.strategy_class = strategy_class
        self.strategy_setting = strategy_setting or {}
        self.rate = float(rate)
        self.slippage = float(slippage)
        self.size = float(size)
        self.pricetick = float(pricetick) if pricetick > 0 else 0.01
        self.capital = float(capital)
        self.weights = weights

        # 按 symbol 切分数据
        self.symbol_data: dict[str, pd.DataFrame] = {
            s: data[data["symbol"].astype(str) == s].copy()
            for s in self.symbols
        }
        # 过滤空数据
        self.symbol_data = {s: df for s, df in self.symbol_data.items() if not df.empty}
        if not self.symbol_data:
            raise ValueError("各标的数据均为空")
        self.symbols = list(self.symbol_data.keys())

        # 资金分配
        self.symbol_capital = _allocate_capital(self.symbols, self.capital, self.weights)

    def run_backtesting(self) -> PortfolioBacktestResult:
        """运行组合回测。"""
        per_symbol_results: dict[str, BacktestResult] = {}
        for symbol in self.symbols:
            df = self.symbol_data[symbol]
            capital = self.symbol_capital[symbol]
            engine = CtaBacktestingEngine(
                data=df,
                strategy_class=self.strategy_class,
                strategy_setting=self.strategy_setting,
                rate=self.rate,
                slippage=self.slippage,
                size=self.size,
                pricetick=self.pricetick,
                capital=capital,
            )
            result = engine.run_backtesting()
            per_symbol_results[symbol] = result

        # 合并结果
        merged_daily = _merge_daily_results(per_symbol_results, self.capital)
        merged_trades = _merge_trades(per_symbol_results)
        logs = _merge_logs(per_symbol_results)

        # 计算组合级统计
        total_return = 0.0
        final_cash = self.capital
        max_drawdown = 0.0
        trade_count = 0
        win_rate = 0.0

        if not merged_daily.empty:
            final_cash = float(merged_daily["equity"].iloc[-1])
            total_return = final_cash / self.capital - 1
            highlevel = merged_daily["equity"].expanding().max()
            ddpercent = merged_daily["equity"] / highlevel - 1
            max_drawdown = float(ddpercent.min())
            trade_count = int(merged_daily["trade_count"].sum())

        # 计算组合级胜率（基于交易盈亏）
        if not merged_trades.empty:
            # 复用 performance 里的交易匹配逻辑较复杂，这里简化：
            # 取各子账户胜率的加权平均
            total_trades = sum(r.trade_count for r in per_symbol_results.values())
            if total_trades > 0:
                weighted_win_rate = sum(
                    r.win_rate * r.trade_count for r in per_symbol_results.values()
                ) / total_trades
                win_rate = weighted_win_rate

        equity_curve = merged_daily[["date", "equity"]].copy() if not merged_daily.empty else pd.DataFrame()

        # 构建 compatible statistics
        stats: dict[str, Any] = {}
        if not merged_daily.empty:
            metrics = calculate_performance(
                daily_df=merged_daily,
                trades_df=merged_trades,
                capital=self.capital,
            )
            stats = metrics.to_dict()
            stats["start_date"] = str(merged_daily["date"].iloc[0].date())
            stats["end_date"] = str(merged_daily["date"].iloc[-1].date())
            stats["capital"] = self.capital
            stats["end_balance"] = final_cash
            stats["total_commission"] = float(merged_daily["commission"].sum())
            stats["daily_commission"] = float(merged_daily["commission"].mean())
            stats["total_turnover"] = float(merged_daily["turnover"].sum())
            stats["daily_turnover"] = float(merged_daily["turnover"].mean())
            stats["total_trade_count"] = trade_count
            stats["daily_trade_count"] = float(merged_daily["trade_count"].mean())

        return PortfolioBacktestResult(
            initial_cash=self.capital,
            final_cash=final_cash,
            total_return=total_return,
            max_drawdown=max_drawdown,
            trade_count=trade_count,
            win_rate=win_rate,
            equity_curve=equity_curve,
            trades=merged_trades,
            daily_results=merged_daily,
            statistics=stats,
            per_symbol_results=per_symbol_results,
            logs=logs,
        )


def run_portfolio_backtest(
    data: pd.DataFrame,
    strategy_name: str,
    symbols: list[str] | None = None,
    weights: dict[str, float] | None = None,
    strategy_setting: dict[str, Any] | None = None,
    initial_cash: float = 100000.0,
    fee_rate: float = 0.0003,
    slippage: float = 0.0,
    size: float = 1.0,
    pricetick: float = 0.01,
) -> PortfolioBacktestResult:
    """
    便捷的组合回测入口。

    Args:
        data: 多标的长格式 DataFrame，必须包含 symbol, date, open, high, low, close, volume
        strategy_name: 策略名称键
        symbols: 要回测的标的列表，默认使用数据中所有 symbol
        weights: 资金权重字典，默认等权
        strategy_setting: 策略参数
        initial_cash: 组合总初始资金
        fee_rate: 手续费率
        slippage: 滑点
        size: 合约乘数
        pricetick: 最小价格变动
    """
    spec = get_strategy_spec(strategy_name)
    if not spec.strategy_class:
        raise ValueError(f"策略 {strategy_name} 不支持组合回测（缺少策略类）")
    if spec.engine_type != "cta":
        raise ValueError(f"策略 {strategy_name} 的引擎类型为 {spec.engine_type}，组合回测仅支持 cta 类型策略")

    engine = PortfolioBacktestEngine(
        data=data,
        strategy_class=spec.strategy_class,
        strategy_setting=strategy_setting,
        symbols=symbols,
        weights=weights,
        rate=fee_rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        capital=initial_cash,
    )
    return engine.run_backtesting()
