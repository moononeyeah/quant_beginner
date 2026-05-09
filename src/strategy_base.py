from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from copy import copy
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, pstdev
from typing import Any, Callable

import pandas as pd


@dataclass
class MarketBar:
    symbol: str
    datetime: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float = 0.0
    turnover: float = 0.0


@dataclass
class OrderRecord:
    orderid: str
    direction: str
    offset: str
    price: float
    volume: float
    traded: float
    status: str
    datetime: datetime
    stop: bool = False

    @property
    def vt_orderid(self) -> str:
        return self.orderid

    def is_active(self) -> bool:
        return self.status in {"submitting", "not_traded"}


@dataclass
class TradeRecord:
    tradeid: str
    orderid: str
    symbol: str
    direction: str
    offset: str
    price: float
    volume: float
    datetime: datetime
    commission: float = 0.0
    slippage: float = 0.0


@dataclass
class StopOrderRecord:
    stop_orderid: str
    symbol: str
    direction: str
    offset: str
    price: float
    volume: float
    datetime: datetime
    status: str = "waiting"


@dataclass
class DailyResult:
    date: datetime
    close_price: float
    trades: list[TradeRecord] = field(default_factory=list)
    pre_close: float = 0.0
    start_pos: float = 0.0
    end_pos: float = 0.0
    turnover: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    trading_pnl: float = 0.0
    holding_pnl: float = 0.0
    total_pnl: float = 0.0
    net_pnl: float = 0.0
    trade_count: int = 0

    def add_trade(self, trade: TradeRecord) -> None:
        self.trades.append(trade)

    def calculate_pnl(
        self,
        pre_close: float,
        start_pos: float,
        size: float,
        rate: float,
        slippage: float,
    ) -> None:
        self.pre_close = pre_close or self.close_price
        self.start_pos = start_pos
        self.end_pos = start_pos
        self.holding_pnl = self.start_pos * (self.close_price - self.pre_close) * size

        self.trade_count = len(self.trades)
        for trade in self.trades:
            pos_change = trade.volume if trade.direction == "long" else -trade.volume
            turnover = trade.volume * size * trade.price
            self.end_pos += pos_change
            self.turnover += turnover
            self.commission += turnover * rate
            self.slippage += trade.volume * size * slippage
            self.trading_pnl += pos_change * (self.close_price - trade.price) * size

        self.total_pnl = self.trading_pnl + self.holding_pnl
        self.net_pnl = self.total_pnl - self.commission - self.slippage


class ArrayManager:
    def __init__(self, size: int = 100) -> None:
        self.size = max(int(size), 10)
        self.opens: deque[float] = deque(maxlen=self.size)
        self.highs: deque[float] = deque(maxlen=self.size)
        self.lows: deque[float] = deque(maxlen=self.size)
        self.closes: deque[float] = deque(maxlen=self.size)
        self.volumes: deque[float] = deque(maxlen=self.size)

    @property
    def inited(self) -> bool:
        return len(self.closes) >= self.size

    def update_bar(self, bar: MarketBar) -> None:
        self.opens.append(float(bar.open_price))
        self.highs.append(float(bar.high_price))
        self.lows.append(float(bar.low_price))
        self.closes.append(float(bar.close_price))
        self.volumes.append(float(bar.volume))

    def _series(self, values: deque[float]) -> pd.Series:
        return pd.Series(list(values), dtype=float)

    def sma(self, window: int, array: bool = False):
        series = self._series(self.closes).rolling(window=window, min_periods=1).mean()
        if array:
            return series.to_numpy()
        return float(series.iloc[-1]) if not series.empty else 0.0

    def std(self, window: int) -> float:
        series = self._series(self.closes).rolling(window=window, min_periods=1).std(ddof=0).fillna(0.0)
        return float(series.iloc[-1]) if not series.empty else 0.0

    def rsi(self, window: int) -> float:
        closes = self._series(self.closes)
        if closes.empty:
            return 50.0
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=window, min_periods=1).mean()
        avg_loss = loss.rolling(window=window, min_periods=1).mean()
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.fillna(50.0).iloc[-1])

    def atr(self, window: int, array: bool = False):
        highs = self._series(self.highs)
        lows = self._series(self.lows)
        closes = self._series(self.closes)
        prev_close = closes.shift(1).fillna(closes)
        tr = pd.concat(
            [
                highs - lows,
                (highs - prev_close).abs(),
                (lows - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(window=window, min_periods=1).mean()
        if array:
            return atr.to_numpy()
        return float(atr.iloc[-1]) if not atr.empty else 0.0

    def boll(self, window: int, dev: float) -> tuple[float, float]:
        mid = self.sma(window)
        std = self.std(window)
        return float(mid + std * dev), float(mid - std * dev)

    def cci(self, window: int) -> float:
        highs = self._series(self.highs)
        lows = self._series(self.lows)
        closes = self._series(self.closes)
        typical = (highs + lows + closes) / 3
        ma = typical.rolling(window=window, min_periods=1).mean()
        md = typical.rolling(window=window, min_periods=1).apply(
            lambda s: float((s - s.mean()).abs().mean()),
            raw=False,
        ).replace(0, pd.NA)
        cci = (typical - ma) / (0.015 * md)
        return float(cci.fillna(0.0).iloc[-1]) if not cci.empty else 0.0

    def donchian(self, window: int) -> tuple[float, float]:
        highs = self._series(self.highs).rolling(window=window, min_periods=1).max()
        lows = self._series(self.lows).rolling(window=window, min_periods=1).min()
        return float(highs.iloc[-1]), float(lows.iloc[-1])

    def keltner(self, window: int, dev: float) -> tuple[float, float]:
        mid = self.sma(window)
        atr = self.atr(window)
        return float(mid + atr * dev), float(mid - atr * dev)


class BarGenerator:
    def __init__(
        self,
        on_bar: Callable[[MarketBar], None],
        window: int = 0,
        on_window_bar: Callable[[MarketBar], None] | None = None,
    ) -> None:
        self.on_bar = on_bar
        self.window = window
        self.on_window_bar = on_window_bar
        self.window_bar: MarketBar | None = None

    def update_tick(self, tick: Any) -> None:
        return

    def update_bar(self, bar: MarketBar) -> None:
        if not self.window or not self.on_window_bar:
            self.on_bar(bar)
            return

        if self.window_bar is None:
            self.window_bar = MarketBar(
                symbol=bar.symbol,
                datetime=bar.datetime,
                open_price=bar.open_price,
                high_price=bar.high_price,
                low_price=bar.low_price,
                close_price=bar.close_price,
                volume=bar.volume,
                turnover=bar.turnover,
            )
        else:
            self.window_bar.high_price = max(self.window_bar.high_price, bar.high_price)
            self.window_bar.low_price = min(self.window_bar.low_price, bar.low_price)
            self.window_bar.close_price = bar.close_price
            self.window_bar.volume += bar.volume
            self.window_bar.turnover += bar.turnover

        complete = (bar.datetime.minute + 1) % self.window == 0
        if complete:
            self.on_window_bar(self.window_bar)
            self.window_bar = None


class CtaTemplate(ABC):
    author: str = ""
    parameters: list[str] = []
    variables: list[str] = []

    def __init__(self, cta_engine: Any, strategy_name: str, vt_symbol: str, setting: dict[str, Any]) -> None:
        self.cta_engine = cta_engine
        self.strategy_name = strategy_name
        self.vt_symbol = vt_symbol
        self.inited = False
        self.trading = False
        self.pos = 0.0
        self.variables = copy(self.variables)
        self.variables[:0] = ["inited", "trading", "pos"]
        self.update_setting(setting)

    def update_setting(self, setting: dict[str, Any]) -> None:
        for name in self.parameters:
            if name in setting:
                setattr(self, name, setting[name])

    @classmethod
    def get_class_parameters(cls) -> dict[str, Any]:
        return {name: getattr(cls, name) for name in cls.parameters}

    def get_parameters(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.parameters}

    def get_variables(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.variables}

    @abstractmethod
    def on_init(self) -> None:
        return

    def on_start(self) -> None:
        return

    def on_stop(self) -> None:
        return

    def on_tick(self, tick: Any) -> None:
        return

    def on_bar(self, bar: MarketBar) -> None:
        return

    def on_trade(self, trade: TradeRecord) -> None:
        return

    def on_order(self, order: OrderRecord) -> None:
        return

    def on_stop_order(self, stop_order: StopOrderRecord) -> None:
        return

    def buy(self, price: float, volume: float, stop: bool = False) -> list[str]:
        return self.send_order("long", "open", price, volume, stop)

    def sell(self, price: float, volume: float, stop: bool = False) -> list[str]:
        return self.send_order("short", "close", price, volume, stop)

    def short(self, price: float, volume: float, stop: bool = False) -> list[str]:
        return self.send_order("short", "open", price, volume, stop)

    def cover(self, price: float, volume: float, stop: bool = False) -> list[str]:
        return self.send_order("long", "close", price, volume, stop)

    def send_order(self, direction: str, offset: str, price: float, volume: float, stop: bool = False) -> list[str]:
        if not self.trading:
            return []
        return self.cta_engine.send_order(self, direction, offset, price, volume, stop)

    def cancel_order(self, vt_orderid: str) -> None:
        if self.trading:
            self.cta_engine.cancel_order(self, vt_orderid)

    def cancel_all(self) -> None:
        if self.trading:
            self.cta_engine.cancel_all(self)

    def write_log(self, msg: str) -> None:
        self.cta_engine.write_log(msg, self)

    def load_bar(self, days: int, callback: Callable[[MarketBar], None] | None = None) -> None:
        if callback is None:
            callback = self.on_bar
        self.cta_engine.load_bar(days, callback)

    def put_event(self) -> None:
        return

    def get_pricetick(self) -> float:
        return float(self.cta_engine.pricetick)

    def get_size(self) -> float:
        return float(self.cta_engine.size)


class CtaSignal(ABC):
    def __init__(self) -> None:
        self.signal_pos = 0

    def on_tick(self, tick: Any) -> None:
        return

    @abstractmethod
    def on_bar(self, bar: MarketBar) -> None:
        return

    def set_signal_pos(self, pos: int) -> None:
        self.signal_pos = pos

    def get_signal_pos(self) -> int:
        return int(self.signal_pos)


class TargetPosTemplate(CtaTemplate):
    tick_add = 1.0

    def __init__(self, cta_engine: Any, strategy_name: str, vt_symbol: str, setting: dict[str, Any]) -> None:
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.last_bar: MarketBar | None = None
        self.target_pos = 0.0
        self.active_orderids: list[str] = []
        self.cancel_orderids: list[str] = []
        self.variables.append("target_pos")

    def on_bar(self, bar: MarketBar) -> None:
        self.last_bar = bar

    def on_order(self, order: OrderRecord) -> None:
        if not order.is_active():
            if order.vt_orderid in self.active_orderids:
                self.active_orderids.remove(order.vt_orderid)
            if order.vt_orderid in self.cancel_orderids:
                self.cancel_orderids.remove(order.vt_orderid)

    def set_target_pos(self, target_pos: float) -> None:
        self.target_pos = target_pos
        self.trade()

    def trade(self) -> None:
        if self.active_orderids:
            for vt_orderid in list(self.active_orderids):
                if vt_orderid not in self.cancel_orderids:
                    self.cancel_order(vt_orderid)
                    self.cancel_orderids.append(vt_orderid)
            return
        self.send_new_order()

    def send_new_order(self) -> None:
        pos_change = self.target_pos - self.pos
        if not pos_change or not self.last_bar:
            return

        if pos_change > 0:
            long_price = self.last_bar.close_price + self.tick_add * self.get_pricetick()
            vt_orderids = self.buy(long_price, abs(pos_change))
        else:
            short_price = max(self.last_bar.close_price - self.tick_add * self.get_pricetick(), self.get_pricetick())
            vt_orderids = self.short(short_price, abs(pos_change))

        self.active_orderids.extend(vt_orderids)


def summarize_returns(returns: list[float]) -> tuple[float, float]:
    if not returns:
        return 0.0, 0.0
    return float(mean(returns)), float(pstdev(returns)) if len(returns) > 1 else 0.0
