from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """完整的回测绩效指标集合。"""

    # 基础收益
    total_return: float = 0.0
    annual_return: float = 0.0
    daily_return: float = 0.0
    daily_return_std: float = 0.0

    # 风险指标
    max_drawdown: float = 0.0
    max_ddpercent: float = 0.0
    max_drawdown_duration: int = 0
    annual_volatility: float = 0.0
    daily_volatility: float = 0.0

    # 风险调整收益
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    return_drawdown_ratio: float = 0.0

    # 交易统计
    total_trade_count: int = 0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0

    # 时间统计
    total_days: int = 0
    profit_days: int = 0
    loss_days: int = 0
    day_win_rate: float = 0.0
    profit_weeks: int = 0
    loss_weeks: int = 0
    week_win_rate: float = 0.0
    profit_months: int = 0
    loss_months: int = 0
    month_win_rate: float = 0.0

    # 分布特征
    skewness: float = 0.0
    kurtosis: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0

    # 原始数据
    monthly_returns: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    weekly_returns: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的字典。"""
        result: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if isinstance(value, pd.DataFrame):
                continue
            if isinstance(value, (np.floating, np.integer)):
                value = float(value) if isinstance(value, np.floating) else int(value)
            result[key] = value
        return result

    def to_display_dict(self) -> dict[str, Any]:
        """用于前端展示的格式化字典。"""
        d = self.to_dict()
        return d


def calculate_max_drawdown_duration(equity_series: pd.Series, date_index: pd.DatetimeIndex) -> int:
    """
    计算最大回撤持续期（从净值高点到后续最低点的连续交易日数）。
    修复了原实现中只计算最低点到结束日期的 bug。
    """
    if equity_series.empty:
        return 0

    high_water_mark = equity_series.expanding().max()
    drawdown = equity_series - high_water_mark

    max_dd_idx = drawdown.idxmin()
    if pd.isna(max_dd_idx):
        return 0

    # 找到最大回撤开始点：在该最低点之前，净值最后一次达到高点的位置
    try:
        loc = date_index.get_loc(max_dd_idx)
    except KeyError:
        return 0

    # 向前找到高点
    pre_equity = equity_series.iloc[: loc + 1]
    pre_hwm = pre_equity.expanding().max()
    # 找到 HWM 最后一次等于当前 equity 值的位置
    hwm_at_dd = pre_hwm.iloc[loc]
    # 找最后一次 equity == hwm_at_dd 的位置
    peak_locs = pre_equity[pre_equity == hwm_at_dd].index
    if peak_locs.empty:
        return 0
    peak_idx = peak_locs[-1]

    try:
        peak_loc = date_index.get_loc(peak_idx)
        duration = loc - peak_loc
        return int(duration)
    except KeyError:
        return 0


def _calculate_trade_metrics_for_symbol(trades_df: pd.DataFrame) -> dict[str, float]:
    """对单个 symbol 的成交记录计算交易级绩效指标（简化版 FIFO）。"""
    if trades_df.empty or "direction" not in trades_df.columns:
        return {
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "avg_profit": 0.0,
            "avg_loss": 0.0,
            "max_profit": 0.0,
            "max_loss": 0.0,
        }

    profits: list[float] = []
    long_stack: list[tuple[float, float]] = []
    short_stack: list[tuple[float, float]] = []

    for _, row in trades_df.iterrows():
        direction = str(row.get("direction", "")).lower()
        offset = str(row.get("offset", "")).lower()
        price = float(row.get("price", 0.0))
        volume = float(row.get("volume", 0.0))
        if volume <= 0 or price <= 0:
            continue

        if direction == "long" and offset == "open":
            long_stack.append((price, volume))
        elif direction == "short" and offset == "open":
            short_stack.append((price, volume))
        elif direction == "short" and offset == "close" and long_stack:
            remain = volume
            while remain > 0 and long_stack:
                entry_price, entry_vol = long_stack[0]
                trade_vol = min(remain, entry_vol)
                profit = (price - entry_price) / entry_price if entry_price else 0.0
                profits.append(profit)
                remain -= trade_vol
                if trade_vol >= entry_vol:
                    long_stack.pop(0)
                else:
                    long_stack[0] = (entry_price, entry_vol - trade_vol)
        elif direction == "long" and offset == "close" and short_stack:
            remain = volume
            while remain > 0 and short_stack:
                entry_price, entry_vol = short_stack[0]
                trade_vol = min(remain, entry_vol)
                profit = (entry_price - price) / entry_price if entry_price else 0.0
                profits.append(profit)
                remain -= trade_vol
                if trade_vol >= entry_vol:
                    short_stack.pop(0)
                else:
                    short_stack[0] = (entry_price, entry_vol - trade_vol)

    if not profits:
        return {
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "avg_profit": 0.0,
            "avg_loss": 0.0,
            "max_profit": 0.0,
            "max_loss": 0.0,
        }

    profit_arr = pd.Series(profits)
    wins = profit_arr[profit_arr > 0]
    losses = profit_arr[profit_arr < 0]

    win_rate = float((profit_arr > 0).mean())
    avg_profit = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.mean()) if not losses.empty else 0.0
    profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float("inf")
    max_profit = float(wins.max()) if not wins.empty else 0.0
    max_loss = float(losses.min()) if not losses.empty else 0.0

    return {
        "win_rate": win_rate,
        "profit_loss_ratio": profit_loss_ratio,
        "avg_profit": avg_profit,
        "avg_loss": avg_loss,
        "max_profit": max_profit,
        "max_loss": max_loss,
    }


def calculate_trade_metrics(trades_df: pd.DataFrame) -> dict[str, float]:
    """
    从成交记录计算交易级绩效指标。
    如果包含 symbol / portfolio_symbol 列，则按标的分组计算后汇总。
    """
    if trades_df.empty or "direction" not in trades_df.columns:
        return {
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "avg_profit": 0.0,
            "avg_loss": 0.0,
            "max_profit": 0.0,
            "max_loss": 0.0,
        }

    symbol_col = None
    for col in ["portfolio_symbol", "symbol"]:
        if col in trades_df.columns:
            symbol_col = col
            break

    if symbol_col:
        # 按 symbol 分组，汇总交易数加权胜率
        total_profits: list[float] = []
        total_trades = 0
        weighted_wins = 0.0
        for symbol, group in trades_df.groupby(symbol_col):
            metrics = _calculate_trade_metrics_for_symbol(group)
            n_trades = len(group)
            total_trades += n_trades
            weighted_wins += metrics["win_rate"] * n_trades
        avg_win_rate = weighted_wins / total_trades if total_trades > 0 else 0.0
        # 盈亏比等用全部数据再算一次（近似）
        all_metrics = _calculate_trade_metrics_for_symbol(trades_df)
        all_metrics["win_rate"] = avg_win_rate
        return all_metrics
    else:
        return _calculate_trade_metrics_for_symbol(trades_df)


def calculate_performance(
    daily_df: pd.DataFrame,
    trades_df: pd.DataFrame | None = None,
    capital: float = 100000.0,
    risk_free_rate: float = 0.03,
) -> PerformanceMetrics:
    """
    根据日度结果和成交记录计算完整绩效指标。

    Args:
        daily_df: 日度盈亏 DataFrame，至少包含 date, net_pnl, equity 列
        trades_df: 成交记录 DataFrame，可选
        capital: 初始资金
        risk_free_rate: 无风险利率（年化），用于计算夏普和索提诺
    """
    metrics = PerformanceMetrics()
    if daily_df.empty or "net_pnl" not in daily_df.columns:
        return metrics

    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if "equity" not in df.columns:
        df["equity"] = df["net_pnl"].cumsum() + capital

    equity = df["equity"]
    returns = equity.pct_change().fillna(0.0)
    net_pnls = df["net_pnl"]

    dates = pd.DatetimeIndex(df["date"])

    # 基础收益
    total_days = len(df)
    end_balance = float(equity.iloc[-1])
    total_return = end_balance / capital - 1
    annual_return = total_return * (240 / total_days) if total_days > 0 else 0.0
    daily_return_mean = float(returns.mean())
    daily_return_std = float(returns.std(ddof=0))

    metrics.total_return = float(total_return)
    metrics.annual_return = float(annual_return)
    metrics.daily_return = daily_return_mean
    metrics.daily_return_std = daily_return_std

    # 风险指标
    highlevel = equity.expanding().max()
    drawdown = equity - highlevel
    ddpercent = equity / highlevel - 1

    max_drawdown = float(drawdown.min())
    max_ddpercent = float(ddpercent.min())
    max_dd_duration = calculate_max_drawdown_duration(equity, dates)

    annual_volatility = daily_return_std * sqrt(240)
    daily_volatility = daily_return_std

    metrics.max_drawdown = max_drawdown
    metrics.max_ddpercent = max_ddpercent
    metrics.max_drawdown_duration = max_dd_duration
    metrics.annual_volatility = annual_volatility
    metrics.daily_volatility = daily_volatility

    # 风险调整收益
    daily_rf = risk_free_rate / 240
    excess_return = daily_return_mean - daily_rf

    sharpe = (excess_return / daily_return_std * sqrt(240)) if daily_return_std > 0 else 0.0

    downside_returns = returns[returns < 0]
    downside_std = float(downside_returns.std(ddof=0)) if not downside_returns.empty else 0.0
    sortino = (excess_return / downside_std * sqrt(240)) if downside_std > 0 else 0.0

    calmar = annual_return / abs(max_ddpercent) if max_ddpercent < 0 else 0.0
    ret_dd_ratio = abs(total_return / max_ddpercent) if max_ddpercent < 0 else 0.0

    metrics.sharpe_ratio = sharpe
    metrics.sortino_ratio = sortino
    metrics.calmar_ratio = calmar
    metrics.return_drawdown_ratio = ret_dd_ratio

    # 时间统计
    profit_days = int((net_pnls > 0).sum())
    loss_days = int((net_pnls < 0).sum())
    day_win_rate = profit_days / (profit_days + loss_days) if (profit_days + loss_days) > 0 else 0.0

    metrics.total_days = total_days
    metrics.profit_days = profit_days
    metrics.loss_days = loss_days
    metrics.day_win_rate = day_win_rate

    # 周统计
    df_weekly = df.set_index("date").resample("W-FRI")["net_pnl"].sum().reset_index()
    if not df_weekly.empty:
        profit_weeks = int((df_weekly["net_pnl"] > 0).sum())
        loss_weeks = int((df_weekly["net_pnl"] < 0).sum())
        metrics.profit_weeks = profit_weeks
        metrics.loss_weeks = loss_weeks
        metrics.week_win_rate = profit_weeks / (profit_weeks + loss_weeks) if (profit_weeks + loss_weeks) > 0 else 0.0
        metrics.weekly_returns = df_weekly.copy()

    # 月统计
    df_monthly = df.set_index("date").resample("ME")["net_pnl"].sum().reset_index()
    if not df_monthly.empty:
        profit_months = int((df_monthly["net_pnl"] > 0).sum())
        loss_months = int((df_monthly["net_pnl"] < 0).sum())
        metrics.profit_months = profit_months
        metrics.loss_months = loss_months
        metrics.month_win_rate = profit_months / (profit_months + loss_months) if (profit_months + loss_months) > 0 else 0.0
        metrics.monthly_returns = df_monthly.copy()

    # 分布特征
    metrics.skewness = float(returns.skew()) if len(returns) > 2 else 0.0
    metrics.kurtosis = float(returns.kurtosis()) if len(returns) > 3 else 0.0
    metrics.var_95 = float(np.percentile(returns, 5)) if len(returns) > 0 else 0.0
    metrics.cvar_95 = float(returns[returns <= metrics.var_95].mean()) if len(returns) > 0 else 0.0

    # 交易统计
    if trades_df is not None and not trades_df.empty:
        trade_metrics = calculate_trade_metrics(trades_df)
        metrics.win_rate = trade_metrics["win_rate"]
        metrics.profit_loss_ratio = trade_metrics["profit_loss_ratio"]
        metrics.avg_profit = trade_metrics["avg_profit"]
        metrics.avg_loss = trade_metrics["avg_loss"]
        metrics.max_profit = trade_metrics["max_profit"]
        metrics.max_loss = trade_metrics["max_loss"]

    # 交易次数
    if "trade_count" in df.columns:
        metrics.total_trade_count = int(df["trade_count"].sum())

    return metrics


def build_statistics_dict(metrics: PerformanceMetrics) -> dict[str, Any]:
    """把 PerformanceMetrics 转成与原 backtest 兼容的 statistics dict。"""
    base = metrics.to_dict()
    # 补充兼容字段
    base["end_balance"] = metrics.total_return * 100000 + 100000  # 近似，调用方应覆盖
    base["total_commission"] = 0.0
    base["daily_commission"] = 0.0
    base["total_turnover"] = 0.0
    base["daily_turnover"] = 0.0
    base["daily_trade_count"] = 0.0
    base["start_date"] = ""
    base["end_date"] = ""
    return base
