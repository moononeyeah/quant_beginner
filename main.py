from __future__ import annotations

import argparse
import json
from typing import Any

import pandas as pd

from config import DEFAULT_FEE_RATE, DEFAULT_INITIAL_CASH, DEFAULT_ROTATION_SYMBOLS
from src.backtest import run_strategy_backtest
from src.data_fetcher import fetch_daily_data
from src.optimizer import optimize_strategy
from src.portfolio_engine import run_portfolio_backtest
from src.plotter import plot_equity_curve, plot_price_with_signals, plot_rotation_selection
from src.rotation_strategy import fetch_rotation_data, parse_rotation_symbols
from src.strategies import STRATEGY_SPECS, get_strategy_spec
from src.utils import format_percent, friendly_error


def _load_price_data(
    strategy_name: str,
    symbol: str,
    start: str,
    end: str,
    frequency: str,
    rotation_symbols: str | list[str] | None = None,
) -> tuple[pd.DataFrame, str]:
    spec = get_strategy_spec(strategy_name)
    if spec.engine_type == "portfolio":
        if frequency != "daily":
            raise ValueError("组合轮动策略仅支持 daily 周期")
        symbols = parse_rotation_symbols(rotation_symbols)
        return fetch_rotation_data(symbols=symbols, start_date=start, end_date=end), ",".join(symbols)

    data = fetch_daily_data(symbol=symbol, start_date=start, end_date=end, frequency=frequency)
    price_data = data.copy()
    price_data["symbol"] = str(symbol).strip()
    return price_data, str(symbol).strip()


def _build_trade_signals(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "datetime" not in trades.columns:
        return pd.DataFrame(columns=["date", "signal"])

    trade_df = trades.copy()
    trade_df["date"] = pd.to_datetime(trade_df["datetime"]).dt.normalize()
    trade_df["signal"] = trade_df["direction"].map({"long": 1, "short": -1}).fillna(0).astype(int)
    return (
        trade_df.groupby("date", as_index=False)["signal"]
        .sum()
        .assign(signal=lambda df: df["signal"].clip(-1, 1))
    )


def _prepare_single_debug(price_data: pd.DataFrame, result) -> pd.DataFrame:
    plot_df = price_data.copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])

    if not result.strategy_output.empty and "date" in result.strategy_output.columns:
        strategy_output = result.strategy_output.copy()
        strategy_output["date"] = pd.to_datetime(strategy_output["date"])
        merge_keys = ["date"]
        if "symbol" in strategy_output.columns and "symbol" in plot_df.columns:
            merge_keys.append("symbol")
        plot_df = plot_df.merge(strategy_output, on=merge_keys, how="left", suffixes=("", "_strategy"))

    signal_df = _build_trade_signals(result.trades)
    if not signal_df.empty:
        plot_df = plot_df.merge(signal_df, on="date", how="left", suffixes=("", "_trade"))

    position_df = result.equity_curve[["date", "position"]].copy() if "position" in result.equity_curve.columns else pd.DataFrame()
    if not position_df.empty:
        position_df["date"] = pd.to_datetime(position_df["date"])
        plot_df = plot_df.merge(position_df, on="date", how="left", suffixes=("", "_equity"))

    if "ma5" not in plot_df.columns or plot_df["ma5"].isna().all():
        plot_df["ma5"] = plot_df["close"].rolling(window=5, min_periods=1).mean()
    if "ma20" not in plot_df.columns or plot_df["ma20"].isna().all():
        plot_df["ma20"] = plot_df["close"].rolling(window=20, min_periods=1).mean()
    if "signal" not in plot_df.columns:
        plot_df["signal"] = 0
    if "position" not in plot_df.columns:
        plot_df["position"] = 0
    if "pct_change" not in plot_df.columns:
        plot_df["pct_change"] = plot_df["close"].pct_change().fillna(0.0)

    plot_df["signal"] = plot_df["signal"].fillna(0).astype(int)
    plot_df["position"] = plot_df["position"].ffill().fillna(0.0)
    return plot_df


def run_pipeline(
    symbol: str,
    start: str,
    end: str,
    initial_cash: float,
    fee_rate: float,
    slippage: float = 0.0,
    frequency: str = "daily",
    strategy_name: str = "double_ma",
    rotation_symbols: str | list[str] | None = None,
    strategy_params: dict[str, Any] | None = None,
):
    strategy_params = strategy_params or {}
    price_data, symbol_label = _load_price_data(
        strategy_name=strategy_name,
        symbol=symbol,
        start=start,
        end=end,
        frequency=frequency,
        rotation_symbols=rotation_symbols,
    )

    result = run_strategy_backtest(
        data=price_data,
        strategy_name=strategy_name,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage=slippage,
        strategy_setting=strategy_params,
    )

    spec = get_strategy_spec(strategy_name)
    if spec.engine_type == "portfolio":
        price_plot = plot_rotation_selection(result.strategy_output)
        equity_plot = plot_equity_curve(result.equity_curve.rename(columns={"holding_symbol": "position"}), strategy_name)
        return price_data, result, price_plot, equity_plot, result.strategy_output.copy(), symbol_label

    debug_df = _prepare_single_debug(price_data, result)
    price_plot = plot_price_with_signals(debug_df, f"{symbol_label}_{frequency}")
    equity_plot = plot_equity_curve(result.equity_curve, f"{symbol_label}_{frequency}")
    return price_data, result, price_plot, equity_plot, debug_df.copy(), symbol_label


def run_optimization_pipeline(
    symbol: str,
    start: str,
    end: str,
    initial_cash: float,
    fee_rate: float,
    slippage: float,
    frequency: str,
    strategy_name: str,
    rotation_symbols: str | list[str] | None,
    strategy_params: dict[str, Any],
    optimization_grid: dict[str, list[Any]],
    use_parallel: bool = True,
    max_workers: int | None = None,
) -> pd.DataFrame:
    price_data, _ = _load_price_data(
        strategy_name=strategy_name,
        symbol=symbol,
        start=start,
        end=end,
        frequency=frequency,
        rotation_symbols=rotation_symbols,
    )
    return optimize_strategy(
        data=price_data,
        strategy_name=strategy_name,
        base_setting=strategy_params,
        optimization_grid=optimization_grid,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage=slippage,
        use_parallel=use_parallel,
        max_workers=max_workers,
    )


def run_portfolio_pipeline(
    symbols: list[str],
    start: str,
    end: str,
    initial_cash: float,
    fee_rate: float,
    slippage: float,
    strategy_name: str = "double_ma",
    weights: dict[str, float] | None = None,
    strategy_params: dict[str, Any] | None = None,
    max_symbol_weight: float | None = None,
    max_drawdown_stop: float | None = None,
):
    """运行组合回测流水线。"""
    from src.rotation_strategy import fetch_rotation_data

    price_data = fetch_rotation_data(symbols=symbols, start_date=start, end_date=end)
    result = run_portfolio_backtest(
        data=price_data,
        strategy_name=strategy_name,
        symbols=symbols,
        weights=weights,
        strategy_setting=strategy_params,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage=slippage,
        max_symbol_weight=max_symbol_weight,
        max_drawdown_stop=max_drawdown_stop,
    )
    return price_data, result, symbols


def _parse_json_dict(raw: str | None, field_name: str) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} 不是合法 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是 JSON 对象")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quant Backtester CLI")
    parser.add_argument("--strategy", default="double_ma", choices=sorted(STRATEGY_SPECS.keys()), help="策略键")
    parser.add_argument("--symbol", default="510300", help="股票或 ETF 代码")
    parser.add_argument("--rotation-symbols", default=",".join(DEFAULT_ROTATION_SYMBOLS), help="轮动策略 ETF 池")
    parser.add_argument("--frequency", default="daily", choices=["daily", "1", "5", "15", "30", "60"], help="K线周期")
    parser.add_argument("--start", required=True, help="开始时间")
    parser.add_argument("--end", required=True, help="结束时间")
    parser.add_argument("--cash", type=float, default=DEFAULT_INITIAL_CASH, help="初始资金")
    parser.add_argument("--fee", type=float, default=DEFAULT_FEE_RATE, help="手续费率")
    parser.add_argument("--slippage", type=float, default=0.0, help="滑点")
    parser.add_argument("--params", default="{}", help="策略参数 JSON")
    parser.add_argument("--optimize", default="", help="优化参数网格 JSON")
    parser.add_argument("--portfolio", action="store_true", help="启用组合回测模式（对多个标的同时回测）")
    parser.add_argument("--portfolio-symbols", default="", help="组合回测标的列表，逗号分隔")
    parser.add_argument("--no-parallel", action="store_true", help="参数优化时禁用多进程")
    parser.add_argument("--max-workers", type=int, default=None, help="参数优化最大并行进程数")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        strategy_params = _parse_json_dict(args.params, "策略参数")
        optimization_grid = _parse_json_dict(args.optimize, "优化参数") if args.optimize else {}

        # 组合回测模式
        if args.portfolio or args.portfolio_symbols:
            from src.rotation_strategy import parse_rotation_symbols
            portfolio_symbols = parse_rotation_symbols(args.portfolio_symbols or args.symbol)
            _, result, symbols = run_portfolio_pipeline(
                symbols=portfolio_symbols,
                start=args.start,
                end=args.end,
                initial_cash=args.cash,
                fee_rate=args.fee,
                slippage=args.slippage,
                strategy_name=args.strategy,
                strategy_params=strategy_params,
            )
            print("组合回测完成")
            print(f"策略类型：{args.strategy}")
            print(f"标的池：{symbols}")
            print(f"标的数量：{len(symbols)}")
            print(f"初始资金：{result.initial_cash:.2f}")
            print(f"最终资金：{result.final_cash:.2f}")
            print(f"总收益率：{format_percent(result.total_return)}")
            print(f"最大回撤：{format_percent(result.max_drawdown)}")
            print(f"交易次数：{result.trade_count}")
            print(f"胜率：{format_percent(result.win_rate)}")
            print(f"总交易日：{result.statistics.get('total_days', 0)}")
            print(f"Sharpe：{result.statistics.get('sharpe_ratio', 0.0):.2f}")
            print(f"Sortino：{result.statistics.get('sortino_ratio', 0.0):.2f}")
            print(f"Calmar：{result.statistics.get('calmar_ratio', 0.0):.2f}")
            print(f"年化收益：{format_percent(result.statistics.get('annual_return', 0.0))}")
            print(f"盈亏比：{result.statistics.get('profit_loss_ratio', 0.0):.2f}")
            print(f"日胜率：{format_percent(result.statistics.get('day_win_rate', 0.0))}")
            print(f"月胜率：{format_percent(result.statistics.get('month_win_rate', 0.0))}")
            return

        if optimization_grid:
            result_df = run_optimization_pipeline(
                symbol=args.symbol,
                start=args.start,
                end=args.end,
                initial_cash=args.cash,
                fee_rate=args.fee,
                slippage=args.slippage,
                frequency=args.frequency,
                strategy_name=args.strategy,
                rotation_symbols=args.rotation_symbols,
                strategy_params=strategy_params,
                optimization_grid=optimization_grid,
                use_parallel=not args.no_parallel,
                max_workers=args.max_workers,
            )
            print(result_df.head(20).to_string(index=False))
            return

        _, result, price_plot, equity_plot, _, symbol_label = run_pipeline(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            initial_cash=args.cash,
            fee_rate=args.fee,
            slippage=args.slippage,
            frequency=args.frequency,
            strategy_name=args.strategy,
            rotation_symbols=args.rotation_symbols,
            strategy_params=strategy_params,
        )
        print("回测完成")
        print(f"策略类型：{args.strategy}")
        print(f"标的：{symbol_label}")
        print(f"数据频率：{args.frequency}")
        print(f"初始资金：{result.initial_cash:.2f}")
        print(f"最终资金：{result.final_cash:.2f}")
        print(f"总收益率：{format_percent(result.total_return)}")
        print(f"最大回撤：{format_percent(result.max_drawdown)}")
        print(f"交易次数：{result.trade_count}")
        print(f"胜率：{format_percent(result.win_rate)}")
        print(f"总交易日：{result.statistics.get('total_days', 0)}")
        print(f"Sharpe：{result.statistics.get('sharpe_ratio', 0.0):.2f}")
        print(f"Sortino：{result.statistics.get('sortino_ratio', 0.0):.2f}")
        print(f"Calmar：{result.statistics.get('calmar_ratio', 0.0):.2f}")
        print(f"年化收益：{format_percent(result.statistics.get('annual_return', 0.0))}")
        print(f"盈亏比：{result.statistics.get('profit_loss_ratio', 0.0):.2f}")
        print(f"K线指标图：{price_plot}")
        print(f"资金曲线图：{equity_plot}")
    except Exception as exc:
        print(friendly_error("运行回测失败，请检查代码、时间格式、依赖安装和网络连接。", exc))


if __name__ == "__main__":
    main()
