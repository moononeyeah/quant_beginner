from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import product
from math import sqrt
from typing import Any, Callable

import pandas as pd

from src.performance import calculate_performance
from src.strategy_base import DailyResult, MarketBar, OrderRecord, StopOrderRecord, TradeRecord
from src.strategies import STRATEGY_SPECS, get_strategy_spec


@dataclass
class BacktestResult:
    initial_cash: float
    final_cash: float
    total_return: float
    max_drawdown: float
    trade_count: int
    win_rate: float
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    daily_results: pd.DataFrame
    statistics: dict[str, Any]
    strategy_output: pd.DataFrame
    logs: list[str]


def _safe_price(value: Any, fallback: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return float(fallback)
    return float(number)


class CtaBacktestingEngine:
    gateway_name = "BACKTESTING"

    def __init__(
        self,
        data: pd.DataFrame,
        strategy_class: type,
        strategy_setting: dict[str, Any] | None = None,
        rate: float = 0.0003,
        slippage: float = 0.0,
        size: float = 1.0,
        pricetick: float = 0.01,
        capital: float = 100000.0,
    ) -> None:
        self.data = data.copy()
        if self.data.empty:
            raise ValueError("无法回测：数据为空")
        self.data["date"] = pd.to_datetime(self.data["date"])
        if "symbol" not in self.data.columns:
            self.data["symbol"] = "DEFAULT"
        symbols = self.data["symbol"].astype(str).unique().tolist()
        if len(symbols) != 1:
            raise ValueError("CTA 回测引擎仅支持单标的，请传入单一 symbol 数据")

        self.symbol = symbols[0]
        self.rate = float(rate)
        self.slippage = float(slippage)
        self.size = float(size)
        self.pricetick = float(pricetick) if pricetick > 0 else 0.01
        self.capital = float(capital)
        self.strategy_class = strategy_class
        self.strategy_setting = strategy_setting or {}

        self.history_data = self._to_bars(self.data)
        self.seed_history = list(self.history_data)
        self.datetime = datetime(1970, 1, 1)
        self.bar: MarketBar | None = None

        self.stop_order_count = 0
        self.stop_orders: dict[str, StopOrderRecord] = {}
        self.active_stop_orders: dict[str, StopOrderRecord] = {}
        self.limit_order_count = 0
        self.limit_orders: dict[str, OrderRecord] = {}
        self.active_limit_orders: dict[str, OrderRecord] = {}
        self.trade_count = 0
        self.trades: dict[str, TradeRecord] = {}
        self.logs: list[str] = []
        self.daily_results: dict[datetime.date, DailyResult] = {}
        self.strategy = strategy_class(self, strategy_class.__name__, self.symbol, self.strategy_setting)

    def _to_bars(self, df: pd.DataFrame) -> list[MarketBar]:
        df = df.sort_values("date").reset_index(drop=True)
        return [
            MarketBar(
                symbol=str(row["symbol"]),
                datetime=pd.Timestamp(row["date"]).to_pydatetime(),
                open_price=_safe_price(row["open"]),
                high_price=_safe_price(row["high"], _safe_price(row["close"])),
                low_price=_safe_price(row["low"], _safe_price(row["close"])),
                close_price=_safe_price(row["close"], _safe_price(row["open"])),
                volume=_safe_price(row.get("volume", 0.0)),
                turnover=_safe_price(row.get("close", 0.0)) * _safe_price(row.get("volume", 0.0)),
            )
            for _, row in df.iterrows()
        ]

    def load_bar(self, days: int, callback: Callable[[MarketBar], None]) -> None:
        if not self.seed_history:
            return
        first = self.seed_history[0].datetime
        last = first
        loaded = 0
        for bar in self.seed_history:
            if bar.datetime.date() != last.date():
                loaded += 1
                last = bar.datetime
            callback(bar)
            if loaded >= days:
                break

    def write_log(self, msg: str, strategy: Any | None = None) -> None:
        prefix = strategy.strategy_name if strategy else "engine"
        self.logs.append(f"{self.datetime} [{prefix}] {msg}")

    def send_order(
        self,
        strategy: Any,
        direction: str,
        offset: str,
        price: float,
        volume: float,
        stop: bool = False,
    ) -> list[str]:
        price = max(round(float(price) / self.pricetick) * self.pricetick, self.pricetick)
        volume = abs(float(volume))
        if volume <= 0:
            return []

        if stop:
            self.stop_order_count += 1
            stop_orderid = f"STOP.{self.stop_order_count}"
            stop_order = StopOrderRecord(
                stop_orderid=stop_orderid,
                symbol=self.symbol,
                direction=direction,
                offset=offset,
                price=price,
                volume=volume,
                datetime=self.datetime,
            )
            self.stop_orders[stop_orderid] = stop_order
            self.active_stop_orders[stop_orderid] = stop_order
            return [stop_orderid]

        self.limit_order_count += 1
        orderid = str(self.limit_order_count)
        order = OrderRecord(
            orderid=orderid,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            traded=0.0,
            status="submitting",
            datetime=self.datetime,
        )
        self.limit_orders[orderid] = order
        self.active_limit_orders[orderid] = order
        return [orderid]

    def cancel_order(self, strategy: Any, vt_orderid: str) -> None:
        if vt_orderid in self.active_limit_orders:
            order = self.active_limit_orders.pop(vt_orderid)
            order.status = "cancelled"
            strategy.on_order(order)
        if vt_orderid in self.active_stop_orders:
            stop_order = self.active_stop_orders.pop(vt_orderid)
            stop_order.status = "cancelled"
            strategy.on_stop_order(stop_order)

    def cancel_all(self, strategy: Any) -> None:
        for vt_orderid in list(self.active_limit_orders.keys()):
            self.cancel_order(strategy, vt_orderid)
        for vt_orderid in list(self.active_stop_orders.keys()):
            self.cancel_order(strategy, vt_orderid)

    def run_backtesting(self) -> BacktestResult:
        self.strategy.on_init()
        self.strategy.inited = True
        self.strategy.trading = True
        self.strategy.on_start()

        for bar in self.history_data:
            self.new_bar(bar)

        self.strategy.trading = False
        self.strategy.on_stop()
        self.calculate_result()
        return self.build_result()

    def new_bar(self, bar: MarketBar) -> None:
        self.bar = bar
        self.datetime = bar.datetime
        self.cross_limit_order()
        self.cross_stop_order()
        self.strategy.on_bar(bar)
        self.update_daily_close(bar.close_price)

    def cross_limit_order(self) -> None:
        if not self.bar:
            return
        long_cross_price = self.bar.low_price
        short_cross_price = self.bar.high_price
        long_best_price = self.bar.open_price
        short_best_price = self.bar.open_price

        for order in list(self.active_limit_orders.values()):
            if order.status == "submitting":
                order.status = "not_traded"
                self.strategy.on_order(order)

            long_cross = order.direction == "long" and order.price >= long_cross_price and long_cross_price > 0
            short_cross = order.direction == "short" and order.price <= short_cross_price and short_cross_price > 0
            if not long_cross and not short_cross:
                continue

            order.traded = order.volume
            order.status = "all_traded"
            self.strategy.on_order(order)
            self.active_limit_orders.pop(order.orderid, None)

            self.trade_count += 1
            trade_price = min(order.price, long_best_price) if long_cross else max(order.price, short_best_price)
            trade = TradeRecord(
                tradeid=str(self.trade_count),
                orderid=order.orderid,
                symbol=self.symbol,
                direction=order.direction,
                offset=order.offset,
                price=trade_price,
                volume=order.volume,
                datetime=self.datetime,
            )
            self.update_trade(trade)

    def cross_stop_order(self) -> None:
        if not self.bar:
            return
        for stop_order in list(self.active_stop_orders.values()):
            long_cross = stop_order.direction == "long" and self.bar.high_price >= stop_order.price
            short_cross = stop_order.direction == "short" and self.bar.low_price <= stop_order.price
            if not long_cross and not short_cross:
                continue

            self.active_stop_orders.pop(stop_order.stop_orderid, None)
            stop_order.status = "triggered"
            self.strategy.on_stop_order(stop_order)

            self.limit_order_count += 1
            orderid = str(self.limit_order_count)
            order = OrderRecord(
                orderid=orderid,
                direction=stop_order.direction,
                offset=stop_order.offset,
                price=stop_order.price,
                volume=stop_order.volume,
                traded=stop_order.volume,
                status="all_traded",
                datetime=self.datetime,
                stop=True,
            )
            self.limit_orders[orderid] = order
            self.strategy.on_order(order)

            self.trade_count += 1
            if long_cross:
                trade_price = max(stop_order.price, self.bar.open_price)
            else:
                trade_price = min(stop_order.price, self.bar.open_price)
            trade = TradeRecord(
                tradeid=str(self.trade_count),
                orderid=orderid,
                symbol=self.symbol,
                direction=order.direction,
                offset=order.offset,
                price=trade_price,
                volume=order.volume,
                datetime=self.datetime,
            )
            self.update_trade(trade)

    def update_trade(self, trade: TradeRecord) -> None:
        self.trades[trade.tradeid] = trade
        self.strategy.pos += trade.volume if trade.direction == "long" else -trade.volume
        self.strategy.on_trade(trade)

    def update_daily_close(self, close_price: float) -> None:
        daily = self.daily_results.get(self.datetime.date())
        if daily:
            daily.close_price = close_price
        else:
            self.daily_results[self.datetime.date()] = DailyResult(self.datetime, close_price)

    def calculate_result(self) -> pd.DataFrame:
        for trade in self.trades.values():
            daily = self.daily_results[trade.datetime.date()]
            daily.add_trade(trade)

        pre_close = 0.0
        start_pos = 0.0
        rows: list[dict[str, Any]] = []
        for daily in self.daily_results.values():
            daily.calculate_pnl(pre_close, start_pos, self.size, self.rate, self.slippage)
            rows.append(
                {
                    "date": pd.Timestamp(daily.date),
                    "close_price": daily.close_price,
                    "pre_close": daily.pre_close,
                    "start_pos": daily.start_pos,
                    "end_pos": daily.end_pos,
                    "turnover": daily.turnover,
                    "commission": daily.commission,
                    "slippage": daily.slippage,
                    "trading_pnl": daily.trading_pnl,
                    "holding_pnl": daily.holding_pnl,
                    "total_pnl": daily.total_pnl,
                    "net_pnl": daily.net_pnl,
                    "trade_count": daily.trade_count,
                }
            )
            pre_close = daily.close_price
            start_pos = daily.end_pos
        return pd.DataFrame(rows)

    def calculate_statistics(self, daily_df: pd.DataFrame) -> dict[str, Any]:
        if daily_df.empty:
            return {}

        trades_df = pd.DataFrame([trade.__dict__ for trade in self.trades.values()])
        metrics = calculate_performance(
            daily_df=daily_df,
            trades_df=trades_df if not trades_df.empty else None,
            capital=self.capital,
        )

        stats = metrics.to_dict()
        # 补充与原接口兼容的字段
        stats["start_date"] = str(pd.Timestamp(daily_df["date"].iloc[0]).date())
        stats["end_date"] = str(pd.Timestamp(daily_df["date"].iloc[-1]).date())
        stats["capital"] = float(self.capital)
        stats["end_balance"] = float(stats.get("total_return", 0.0)) * self.capital + self.capital
        stats["total_commission"] = float(daily_df["commission"].sum())
        stats["daily_commission"] = float(daily_df["commission"].mean())
        stats["total_turnover"] = float(daily_df["turnover"].sum())
        stats["daily_turnover"] = float(daily_df["turnover"].mean())
        stats["total_trade_count"] = int(daily_df["trade_count"].sum())
        stats["daily_trade_count"] = float(daily_df["trade_count"].mean())
        return stats

    def build_result(self) -> BacktestResult:
        daily_df = self.calculate_result()
        statistics = self.calculate_statistics(daily_df)
        if not daily_df.empty:
            daily_df["equity"] = daily_df["net_pnl"].cumsum() + self.capital
            equity_curve = daily_df[["date", "equity", "close_price", "end_pos"]].rename(
                columns={"close_price": "close", "end_pos": "position"}
            )
        else:
            equity_curve = pd.DataFrame(columns=["date", "equity", "close", "position"])
        trades_df = pd.DataFrame([trade.__dict__ for trade in self.trades.values()])
        strategy_output = pd.DataFrame()
        if hasattr(self.strategy, "get_debug_frame"):
            try:
                strategy_output = self.strategy.get_debug_frame()
            except Exception:
                strategy_output = pd.DataFrame()
        return BacktestResult(
            initial_cash=self.capital,
            final_cash=float(statistics.get("end_balance", self.capital)),
            total_return=float(statistics.get("total_return", 0.0)),
            max_drawdown=float(statistics.get("max_ddpercent", 0.0)),
            trade_count=int(statistics.get("total_trade_count", 0)),
            win_rate=float(statistics.get("win_rate", 0.0)),
            equity_curve=equity_curve,
            trades=trades_df,
            daily_results=daily_df,
            statistics=statistics,
            strategy_output=strategy_output,
            logs=self.logs.copy(),
        )


def run_portfolio_rotation_backtest(
    price_data: pd.DataFrame,
    initial_cash: float = 100000.0,
    fee_rate: float = 0.0003,
    slippage: float = 0.0,
    lookback_days: int = 20,
) -> BacktestResult:
    if price_data.empty:
        raise ValueError("无法回测 ETF 轮动：数据为空")
    data = price_data.copy()
    data["date"] = pd.to_datetime(data["date"])
    close_panel = data.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index().ffill()
    open_panel = data.pivot_table(index="date", columns="symbol", values="open", aggfunc="last").sort_index().ffill()
    momentum = close_panel / close_panel.shift(int(lookback_days)) - 1
    month_ends = close_panel.index.to_series().groupby(close_panel.index.to_series().dt.to_period("M")).max().tolist()
    plan_rows: list[dict[str, Any]] = []
    for signal_date in month_ends:
        scores = momentum.loc[signal_date].dropna().sort_values(ascending=False)
        if scores.empty:
            continue
        loc = close_panel.index.get_loc(signal_date)
        if loc >= len(close_panel.index) - 1:
            continue
        execute_date = close_panel.index[loc + 1]
        plan_rows.append(
            {
                "signal_date": pd.Timestamp(signal_date),
                "execute_date": pd.Timestamp(execute_date),
                "target_symbol": str(scores.index[0]),
                "target_return": float(scores.iloc[0]),
                "ranking": " | ".join(f"{symbol}:{value:.2%}" for symbol, value in scores.items()),
            }
        )
    plan = pd.DataFrame(plan_rows)
    if plan.empty:
        raise ValueError("轮动策略未生成有效调仓计划")

    cash = float(initial_cash)
    current_symbol = None
    position = 0.0
    entry_capital = 0.0
    daily_rows = []
    trade_rows = []
    completed_returns: list[float] = []
    plan_map = {pd.Timestamp(row["execute_date"]): row for _, row in plan.iterrows()}

    for date in close_panel.index:
        trade_count = 0
        turnover = 0.0
        commission = 0.0
        trading_pnl = 0.0
        holding_pnl = 0.0

        if current_symbol:
            prev_dates = close_panel.index[close_panel.index < date]
            prev_close = float(close_panel.loc[prev_dates[-1], current_symbol]) if len(prev_dates) else float(close_panel.loc[date, current_symbol])
            holding_pnl = position * (float(close_panel.loc[date, current_symbol]) - prev_close)

        if date in plan_map:
            item = plan_map[date]
            target_symbol = item["target_symbol"]
            if current_symbol and current_symbol != target_symbol:
                sell_price = max(float(open_panel.loc[date, current_symbol]) - slippage, 0.01)
                turnover += position * sell_price
                commission += turnover * fee_rate
                cash += position * sell_price - position * sell_price * fee_rate
                completed_return = cash / entry_capital - 1 if entry_capital else 0.0
                completed_returns.append(completed_return)
                trade_rows.append(
                    {
                        "date": pd.Timestamp(date),
                        "action": "调出",
                        "symbol": current_symbol,
                        "price": sell_price,
                        "volume": position,
                        "profit": completed_return,
                    }
                )
                trade_count += 1
                position = 0.0
                current_symbol = None

            if current_symbol is None:
                buy_price = float(open_panel.loc[date, target_symbol]) + slippage
                volume = cash / (buy_price * (1 + fee_rate))
                buy_turnover = volume * buy_price
                buy_commission = buy_turnover * fee_rate
                turnover += buy_turnover
                commission += buy_commission
                cash -= buy_turnover + buy_commission
                position = volume
                current_symbol = target_symbol
                entry_capital = buy_turnover + buy_commission
                trade_rows.append(
                    {
                        "date": pd.Timestamp(date),
                        "action": "调入",
                        "symbol": target_symbol,
                        "price": buy_price,
                        "volume": volume,
                        "signal_date": item["signal_date"],
                        "target_return": item["target_return"],
                        "ranking": item["ranking"],
                    }
                )
                trade_count += 1

        close_price = float(close_panel.loc[date, current_symbol]) if current_symbol else 0.0
        equity = cash + position * close_price
        total_pnl = holding_pnl + trading_pnl
        net_pnl = total_pnl - commission
        daily_rows.append(
            {
                "date": pd.Timestamp(date),
                "trade_count": trade_count,
                "turnover": turnover,
                "commission": commission,
                "slippage": 0.0,
                "trading_pnl": trading_pnl,
                "holding_pnl": holding_pnl,
                "total_pnl": total_pnl,
                "net_pnl": net_pnl,
                "equity": equity,
                "holding_symbol": current_symbol or "CASH",
            }
        )

    daily_df = pd.DataFrame(daily_rows)
    daily_df["highlevel"] = daily_df["equity"].cummax()
    daily_df["drawdown"] = daily_df["equity"] - daily_df["highlevel"]
    daily_df["ddpercent"] = daily_df["equity"] / daily_df["highlevel"] - 1
    statistics = {
        "start_date": str(pd.Timestamp(daily_df["date"].iloc[0]).date()),
        "end_date": str(pd.Timestamp(daily_df["date"].iloc[-1]).date()),
        "total_days": int(len(daily_df)),
        "profit_days": int((daily_df["net_pnl"] > 0).sum()),
        "loss_days": int((daily_df["net_pnl"] < 0).sum()),
        "capital": initial_cash,
        "end_balance": float(daily_df["equity"].iloc[-1]),
        "max_drawdown": float(daily_df["drawdown"].min()),
        "max_ddpercent": float(daily_df["ddpercent"].min()),
        "max_drawdown_duration": 0,
        "total_net_pnl": float(daily_df["net_pnl"].sum()),
        "daily_net_pnl": float(daily_df["net_pnl"].mean()),
        "total_commission": float(daily_df["commission"].sum()),
        "daily_commission": float(daily_df["commission"].mean()),
        "total_turnover": float(daily_df["turnover"].sum()),
        "daily_turnover": float(daily_df["turnover"].mean()),
        "total_trade_count": int(daily_df["trade_count"].sum()),
        "daily_trade_count": float(daily_df["trade_count"].mean()),
        "total_return": float(daily_df["equity"].iloc[-1] / initial_cash - 1),
        "annual_return": float((daily_df["equity"].iloc[-1] / initial_cash - 1) * (240 / len(daily_df))),
        "daily_return": float(daily_df["equity"].pct_change().fillna(0).mean()),
        "return_std": float(daily_df["equity"].pct_change().fillna(0).std(ddof=0)),
        "sharpe_ratio": 0.0,
        "return_drawdown_ratio": 0.0,
        "win_rate": float((pd.Series(completed_returns) > 0).mean()) if completed_returns else 0.0,
    }
    equity_curve = daily_df[["date", "equity", "holding_symbol"]].copy()
    return BacktestResult(
        initial_cash=float(initial_cash),
        final_cash=float(daily_df["equity"].iloc[-1]),
        total_return=float(statistics["total_return"]),
        max_drawdown=float(statistics["max_ddpercent"]),
        trade_count=int(statistics["total_trade_count"]),
        win_rate=float(statistics["win_rate"]),
        equity_curve=equity_curve,
        trades=pd.DataFrame(trade_rows),
        daily_results=daily_df,
        statistics=statistics,
        strategy_output=plan,
        logs=[],
    )


def run_strategy_backtest(
    data: pd.DataFrame,
    strategy_name: str,
    initial_cash: float = 100000.0,
    fee_rate: float = 0.0003,
    slippage: float = 0.0,
    strategy_setting: dict[str, Any] | None = None,
    size: float = 1.0,
    pricetick: float = 0.01,
) -> BacktestResult:
    spec = get_strategy_spec(strategy_name)
    if spec.engine_type == "portfolio":
        return run_portfolio_rotation_backtest(
            price_data=data,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage=slippage,
            lookback_days=int((strategy_setting or {}).get("lookback_days", 20)),
        )
    if not spec.strategy_class:
        raise ValueError(f"策略 {strategy_name} 没有可运行的策略类")
    engine = CtaBacktestingEngine(
        data=data,
        strategy_class=spec.strategy_class,
        strategy_setting=strategy_setting,
        rate=fee_rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        capital=initial_cash,
    )
    return engine.run_backtesting()


def optimize_strategy(
    data: pd.DataFrame,
    strategy_name: str,
    base_setting: dict[str, Any],
    optimization_grid: dict[str, list[Any]],
    initial_cash: float,
    fee_rate: float,
    slippage: float,
    size: float = 1.0,
    pricetick: float = 0.01,
    target: str = "total_return",
) -> pd.DataFrame:
    if not optimization_grid:
        raise ValueError("参数优化网格为空")
    spec = get_strategy_spec(strategy_name)
    valid_params = set(spec.default_parameters.keys())
    invalid_keys = [key for key in optimization_grid.keys() if key not in valid_params]
    if invalid_keys:
        raise ValueError(f"优化参数不属于当前策略：{invalid_keys}；可用参数为：{sorted(valid_params)}")
    keys = list(optimization_grid.keys())
    rows: list[dict[str, Any]] = []
    for values in product(*[optimization_grid[key] for key in keys]):
        setting = dict(base_setting)
        setting.update(dict(zip(keys, values)))
        result = run_strategy_backtest(
            data=data,
            strategy_name=strategy_name,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage=slippage,
            strategy_setting=setting,
            size=size,
            pricetick=pricetick,
        )
        row = {"strategy": strategy_name, **setting}
        row.update(result.statistics)
        rows.append(row)
    df = pd.DataFrame(rows)
    if target in df.columns:
        df = df.sort_values(target, ascending=False).reset_index(drop=True)
    return df


def run_backtest(df: pd.DataFrame, initial_cash: float = 100000.0, fee_rate: float = 0.0003, slippage: float = 0.0) -> BacktestResult:
    return run_strategy_backtest(
        data=df,
        strategy_name="double_ma",
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage=slippage,
    )


def run_rotation_backtest(
    price_data: pd.DataFrame,
    rebalance_plan: pd.DataFrame | None = None,
    initial_cash: float = 100000.0,
    fee_rate: float = 0.0003,
    slippage: float = 0.0,
) -> BacktestResult:
    _ = rebalance_plan
    return run_strategy_backtest(
        data=price_data,
        strategy_name="rotation",
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage=slippage,
    )
