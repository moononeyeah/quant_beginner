from __future__ import annotations

import numpy as np

from src.strategy_base import ArrayManager, BarGenerator, CtaSignal, CtaTemplate, MarketBar, TargetPosTemplate, TradeRecord


class AtrRsiStrategy(CtaTemplate):
    author = "vnpy"
    atr_length = 22
    atr_ma_length = 10
    rsi_length = 5
    rsi_entry = 16
    trailing_percent = 0.8
    fixed_size = 1

    atr_value = 0.0
    atr_ma = 0.0
    rsi_value = 0.0
    rsi_buy = 0.0
    rsi_sell = 0.0
    intra_trade_high = 0.0
    intra_trade_low = 0.0

    parameters = ["atr_length", "atr_ma_length", "rsi_length", "rsi_entry", "trailing_percent", "fixed_size"]
    variables = ["atr_value", "atr_ma", "rsi_value", "rsi_buy", "rsi_sell", "intra_trade_high", "intra_trade_low"]

    def on_init(self) -> None:
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=max(self.atr_length, self.atr_ma_length, self.rsi_length) + 10)
        self.rsi_buy = 50 + self.rsi_entry
        self.rsi_sell = 50 - self.rsi_entry
        self.load_bar(10)

    def on_bar(self, bar: MarketBar) -> None:
        self.cancel_all()
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        atr_array = self.am.atr(self.atr_length, array=True)
        self.atr_value = float(atr_array[-1])
        self.atr_ma = float(np.mean(atr_array[-self.atr_ma_length:]))
        self.rsi_value = self.am.rsi(self.rsi_length)

        if self.pos == 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = bar.low_price
            if self.atr_value > self.atr_ma:
                if self.rsi_value > self.rsi_buy:
                    self.buy(bar.close_price + 5 * self.get_pricetick(), self.fixed_size)
                elif self.rsi_value < self.rsi_sell:
                    self.short(max(bar.close_price - 5 * self.get_pricetick(), self.get_pricetick()), self.fixed_size)
        elif self.pos > 0:
            self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
            self.intra_trade_low = bar.low_price
            long_stop = self.intra_trade_high * (1 - self.trailing_percent / 100)
            self.sell(long_stop, abs(self.pos), stop=True)
        elif self.pos < 0:
            self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
            self.intra_trade_high = bar.high_price
            short_stop = self.intra_trade_low * (1 + self.trailing_percent / 100)
            self.cover(short_stop, abs(self.pos), stop=True)


class BollChannelStrategy(CtaTemplate):
    author = "vnpy"
    boll_window = 18
    boll_dev = 3.4
    cci_window = 10
    atr_window = 30
    sl_multiplier = 5.2
    fixed_size = 1

    boll_up = 0.0
    boll_down = 0.0
    cci_value = 0.0
    atr_value = 0.0
    intra_trade_high = 0.0
    intra_trade_low = 0.0
    long_stop = 0.0
    short_stop = 0.0

    parameters = ["boll_window", "boll_dev", "cci_window", "atr_window", "sl_multiplier", "fixed_size"]
    variables = ["boll_up", "boll_down", "cci_value", "atr_value", "intra_trade_high", "intra_trade_low", "long_stop", "short_stop"]

    def on_init(self) -> None:
        self.bg = BarGenerator(self.on_bar, 15, self.on_15min_bar)
        self.am = ArrayManager(size=max(self.boll_window, self.cci_window, self.atr_window) + 10)
        self.load_bar(10)

    def on_bar(self, bar: MarketBar) -> None:
        self.bg.update_bar(bar)

    def on_15min_bar(self, bar: MarketBar) -> None:
        self.cancel_all()
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        self.boll_up, self.boll_down = self.am.boll(self.boll_window, self.boll_dev)
        self.cci_value = self.am.cci(self.cci_window)
        self.atr_value = self.am.atr(self.atr_window)

        if self.pos == 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = bar.low_price
            if self.cci_value > 0:
                self.buy(self.boll_up, self.fixed_size, stop=True)
            elif self.cci_value < 0:
                self.short(self.boll_down, self.fixed_size, stop=True)
        elif self.pos > 0:
            self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
            self.intra_trade_low = bar.low_price
            self.long_stop = self.intra_trade_high - self.atr_value * self.sl_multiplier
            self.sell(self.long_stop, abs(self.pos), stop=True)
        elif self.pos < 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
            self.short_stop = self.intra_trade_low + self.atr_value * self.sl_multiplier
            self.cover(self.short_stop, abs(self.pos), stop=True)


class DoubleMaStrategy(CtaTemplate):
    author = "vnpy"
    fast_window = 10
    slow_window = 20
    fast_ma0 = 0.0
    fast_ma1 = 0.0
    slow_ma0 = 0.0
    slow_ma1 = 0.0

    parameters = ["fast_window", "slow_window"]
    variables = ["fast_ma0", "fast_ma1", "slow_ma0", "slow_ma1"]

    def on_init(self) -> None:
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=max(self.fast_window, self.slow_window) + 10)
        self.load_bar(10)

    def on_bar(self, bar: MarketBar) -> None:
        self.cancel_all()
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        fast_ma = self.am.sma(self.fast_window, array=True)
        slow_ma = self.am.sma(self.slow_window, array=True)
        self.fast_ma0 = float(fast_ma[-1])
        self.fast_ma1 = float(fast_ma[-2])
        self.slow_ma0 = float(slow_ma[-1])
        self.slow_ma1 = float(slow_ma[-2])

        cross_over = self.fast_ma0 > self.slow_ma0 and self.fast_ma1 < self.slow_ma1
        cross_below = self.fast_ma0 < self.slow_ma0 and self.fast_ma1 > self.slow_ma1

        if cross_over:
            if self.pos == 0:
                self.buy(bar.close_price, 1)
            elif self.pos < 0:
                self.cover(bar.close_price, abs(self.pos))
                self.buy(bar.close_price, 1)
        elif cross_below:
            if self.pos == 0:
                self.short(bar.close_price, 1)
            elif self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))
                self.short(bar.close_price, 1)


class DualThrustStrategy(CtaTemplate):
    author = "vnpy"
    fixed_size = 1
    k1 = 0.4
    k2 = 0.6
    day_open = 0.0
    day_high = 0.0
    day_low = 0.0
    day_range = 0.0
    long_entry = 0.0
    short_entry = 0.0
    long_entered = False
    short_entered = False

    parameters = ["k1", "k2", "fixed_size"]
    variables = ["day_range", "long_entry", "short_entry"]

    def on_init(self) -> None:
        self.bg = BarGenerator(self.on_bar)
        self.bars: list[MarketBar] = []
        self.exit_hour = 14
        self.exit_minute = 55
        self.load_bar(10)

    def on_bar(self, bar: MarketBar) -> None:
        self.cancel_all()
        self.bars.append(bar)
        if len(self.bars) <= 2:
            return
        self.bars = self.bars[-2:]
        last_bar = self.bars[-2]

        if last_bar.datetime.date() != bar.datetime.date():
            if self.day_high:
                self.day_range = self.day_high - self.day_low
                self.long_entry = bar.open_price + self.k1 * self.day_range
                self.short_entry = bar.open_price - self.k2 * self.day_range
            self.day_open = bar.open_price
            self.day_high = bar.high_price
            self.day_low = bar.low_price
            self.long_entered = False
            self.short_entered = False
        else:
            self.day_high = max(self.day_high, bar.high_price)
            self.day_low = min(self.day_low, bar.low_price)

        if not self.day_range:
            return

        exit_time = bar.datetime.replace(hour=self.exit_hour, minute=self.exit_minute)
        if bar.datetime < exit_time:
            if self.pos == 0:
                if bar.close_price > self.day_open:
                    if not self.long_entered:
                        self.buy(self.long_entry, self.fixed_size, stop=True)
                else:
                    if not self.short_entered:
                        self.short(self.short_entry, self.fixed_size, stop=True)
            elif self.pos > 0:
                self.long_entered = True
                self.sell(self.short_entry, abs(self.pos), stop=True)
                if not self.short_entered:
                    self.short(self.short_entry, self.fixed_size, stop=True)
            elif self.pos < 0:
                self.short_entered = True
                self.cover(self.long_entry, abs(self.pos), stop=True)
                if not self.long_entered:
                    self.buy(self.long_entry, self.fixed_size, stop=True)
        else:
            if self.pos > 0:
                self.sell(bar.close_price * 0.99, abs(self.pos))
            elif self.pos < 0:
                self.cover(bar.close_price * 1.01, abs(self.pos))


class KingKeltnerStrategy(CtaTemplate):
    author = "vnpy"
    kk_length = 11
    kk_dev = 1.6
    trailing_percent = 0.8
    fixed_size = 1

    kk_up = 0.0
    kk_down = 0.0
    intra_trade_high = 0.0
    intra_trade_low = 0.0

    parameters = ["kk_length", "kk_dev", "trailing_percent", "fixed_size"]
    variables = ["kk_up", "kk_down"]

    def on_init(self) -> None:
        self.bg = BarGenerator(self.on_bar, 5, self.on_5min_bar)
        self.am = ArrayManager(size=max(self.kk_length, 20) + 10)
        self.long_vt_orderids: list[str] = []
        self.short_vt_orderids: list[str] = []
        self.vt_orderids: list[str] = []
        self.load_bar(10)

    def on_bar(self, bar: MarketBar) -> None:
        self.bg.update_bar(bar)

    def on_5min_bar(self, bar: MarketBar) -> None:
        for orderid in list(self.vt_orderids):
            self.cancel_order(orderid)
        self.vt_orderids.clear()

        self.am.update_bar(bar)
        if not self.am.inited:
            return

        self.kk_up, self.kk_down = self.am.keltner(self.kk_length, self.kk_dev)
        if self.pos == 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = bar.low_price
            self.send_oco_order(self.kk_up, self.kk_down, self.fixed_size)
        elif self.pos > 0:
            self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
            sell_orderids = self.sell(self.intra_trade_high * (1 - self.trailing_percent / 100), abs(self.pos), stop=True)
            self.vt_orderids.extend(sell_orderids)
        elif self.pos < 0:
            self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
            cover_orderids = self.cover(self.intra_trade_low * (1 + self.trailing_percent / 100), abs(self.pos), stop=True)
            self.vt_orderids.extend(cover_orderids)

    def on_trade(self, trade: TradeRecord) -> None:
        if self.pos != 0:
            if self.pos > 0:
                for orderid in self.short_vt_orderids:
                    self.cancel_order(orderid)
            elif self.pos < 0:
                for orderid in self.long_vt_orderids:
                    self.cancel_order(orderid)

    def send_oco_order(self, buy_price: float, short_price: float, volume: float) -> None:
        self.long_vt_orderids = self.buy(buy_price, volume, stop=True)
        self.short_vt_orderids = self.short(short_price, volume, stop=True)
        self.vt_orderids.extend(self.long_vt_orderids + self.short_vt_orderids)


class RsiSignal(CtaSignal):
    def __init__(self, rsi_window: int, rsi_level: float) -> None:
        super().__init__()
        self.rsi_window = rsi_window
        self.rsi_level = rsi_level
        self.rsi_long = 50 + self.rsi_level
        self.rsi_short = 50 - self.rsi_level
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=max(self.rsi_window, 20) + 10)

    def on_bar(self, bar: MarketBar) -> None:
        self.am.update_bar(bar)
        if not self.am.inited:
            self.set_signal_pos(0)
            return
        rsi_value = self.am.rsi(self.rsi_window)
        if rsi_value >= self.rsi_long:
            self.set_signal_pos(1)
        elif rsi_value <= self.rsi_short:
            self.set_signal_pos(-1)
        else:
            self.set_signal_pos(0)


class CciSignal(CtaSignal):
    def __init__(self, cci_window: int, cci_level: float) -> None:
        super().__init__()
        self.cci_window = cci_window
        self.cci_level = cci_level
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=max(self.cci_window, 20) + 10)

    def on_bar(self, bar: MarketBar) -> None:
        self.am.update_bar(bar)
        if not self.am.inited:
            self.set_signal_pos(0)
            return
        value = self.am.cci(self.cci_window)
        if value >= self.cci_level:
            self.set_signal_pos(1)
        elif value <= -self.cci_level:
            self.set_signal_pos(-1)
        else:
            self.set_signal_pos(0)


class MaSignal(CtaSignal):
    def __init__(self, fast_window: int, slow_window: int) -> None:
        super().__init__()
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.bg = BarGenerator(self.on_bar, 5, self.on_5min_bar)
        self.am = ArrayManager(size=max(self.fast_window, self.slow_window) + 10)

    def on_bar(self, bar: MarketBar) -> None:
        self.bg.update_bar(bar)

    def on_5min_bar(self, bar: MarketBar) -> None:
        self.am.update_bar(bar)
        if not self.am.inited:
            self.set_signal_pos(0)
            return
        fast_ma = self.am.sma(self.fast_window)
        slow_ma = self.am.sma(self.slow_window)
        if fast_ma > slow_ma:
            self.set_signal_pos(1)
        elif fast_ma < slow_ma:
            self.set_signal_pos(-1)
        else:
            self.set_signal_pos(0)


class MultiSignalStrategy(TargetPosTemplate):
    author = "vnpy"
    rsi_window = 14
    rsi_level = 20
    cci_window = 30
    cci_level = 10
    fast_window = 5
    slow_window = 20
    parameters = ["rsi_window", "rsi_level", "cci_window", "cci_level", "fast_window", "slow_window"]

    def on_init(self) -> None:
        self.rsi_signal = RsiSignal(self.rsi_window, self.rsi_level)
        self.cci_signal = CciSignal(self.cci_window, self.cci_level)
        self.ma_signal = MaSignal(self.fast_window, self.slow_window)
        self.signal_pos = {"rsi": 0, "cci": 0, "ma": 0}
        self.load_bar(10)

    def on_bar(self, bar: MarketBar) -> None:
        super().on_bar(bar)
        self.rsi_signal.on_bar(bar)
        self.cci_signal.on_bar(bar)
        self.ma_signal.on_bar(bar)
        self.calculate_target_pos()

    def calculate_target_pos(self) -> None:
        self.signal_pos["rsi"] = self.rsi_signal.get_signal_pos()
        self.signal_pos["cci"] = self.cci_signal.get_signal_pos()
        self.signal_pos["ma"] = self.ma_signal.get_signal_pos()
        self.set_target_pos(sum(self.signal_pos.values()))


class MultiTimeframeStrategy(CtaTemplate):
    author = "vnpy"
    rsi_signal = 20
    rsi_window = 14
    fast_window = 5
    slow_window = 20
    fixed_size = 1

    rsi_value = 0.0
    rsi_long = 0.0
    rsi_short = 0.0
    fast_ma = 0.0
    slow_ma = 0.0
    ma_trend = 0.0

    parameters = ["rsi_signal", "rsi_window", "fast_window", "slow_window", "fixed_size"]
    variables = ["rsi_value", "rsi_long", "rsi_short", "fast_ma", "slow_ma", "ma_trend"]

    def on_init(self) -> None:
        self.rsi_long = 50 + self.rsi_signal
        self.rsi_short = 50 - self.rsi_signal
        self.bg5 = BarGenerator(self.on_bar, 5, self.on_5min_bar)
        self.am5 = ArrayManager(size=max(self.rsi_window, 20) + 10)
        self.bg15 = BarGenerator(self.on_bar, 15, self.on_15min_bar)
        self.am15 = ArrayManager(size=max(self.fast_window, self.slow_window) + 10)
        self.load_bar(10)

    def on_bar(self, bar: MarketBar) -> None:
        self.bg5.update_bar(bar)
        self.bg15.update_bar(bar)

    def on_5min_bar(self, bar: MarketBar) -> None:
        self.cancel_all()
        self.am5.update_bar(bar)
        if not self.am5.inited or not self.ma_trend:
            return
        self.rsi_value = self.am5.rsi(self.rsi_window)
        if self.pos == 0:
            if self.ma_trend > 0 and self.rsi_value >= self.rsi_long:
                self.buy(bar.close_price + 5 * self.get_pricetick(), self.fixed_size)
            elif self.ma_trend < 0 and self.rsi_value <= self.rsi_short:
                self.short(max(bar.close_price - 5 * self.get_pricetick(), self.get_pricetick()), self.fixed_size)
        elif self.pos > 0:
            if self.ma_trend < 0 or self.rsi_value < 50:
                self.sell(max(bar.close_price - 5 * self.get_pricetick(), self.get_pricetick()), abs(self.pos))
        elif self.pos < 0:
            if self.ma_trend > 0 or self.rsi_value > 50:
                self.cover(bar.close_price + 5 * self.get_pricetick(), abs(self.pos))

    def on_15min_bar(self, bar: MarketBar) -> None:
        self.am15.update_bar(bar)
        if not self.am15.inited:
            return
        self.fast_ma = self.am15.sma(self.fast_window)
        self.slow_ma = self.am15.sma(self.slow_window)
        self.ma_trend = 1 if self.fast_ma > self.slow_ma else -1


class TestStrategy(CtaTemplate):
    author = "vnpy"
    test_trigger = 10
    tick_count = 0
    test_all_done = False
    parameters = ["test_trigger"]
    variables = ["tick_count", "test_all_done"]

    def on_init(self) -> None:
        self.test_funcs = [
            self.test_market_order,
            self.test_limit_order,
            self.test_cancel_all,
            self.test_stop_order,
        ]
        self.last_bar: MarketBar | None = None

    def on_bar(self, bar: MarketBar) -> None:
        if self.test_all_done:
            return
        self.last_bar = bar
        self.tick_count += 1
        if self.tick_count >= self.test_trigger:
            self.tick_count = 0
            if self.test_funcs:
                test_func = self.test_funcs.pop(0)
                test_func()
            else:
                self.test_all_done = True

    def test_market_order(self) -> None:
        if self.last_bar:
            self.buy(self.last_bar.close_price * 1.01, 1)

    def test_limit_order(self) -> None:
        if self.last_bar:
            self.buy(self.last_bar.close_price * 0.99, 1)

    def test_stop_order(self) -> None:
        if self.last_bar:
            self.buy(self.last_bar.close_price * 1.005, 1, stop=True)

    def test_cancel_all(self) -> None:
        self.cancel_all()


class TurtleSignalStrategy(CtaTemplate):
    author = "vnpy"
    entry_window = 20
    exit_window = 10
    atr_window = 20
    fixed_size = 1

    entry_up = 0.0
    entry_down = 0.0
    exit_up = 0.0
    exit_down = 0.0
    atr_value = 0.0
    long_entry = 0.0
    short_entry = 0.0
    long_stop = 0.0
    short_stop = 0.0

    parameters = ["entry_window", "exit_window", "atr_window", "fixed_size"]
    variables = ["entry_up", "entry_down", "exit_up", "exit_down", "atr_value"]

    def on_init(self) -> None:
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=max(self.entry_window, self.exit_window, self.atr_window) + 10)
        self.load_bar(20)

    def on_bar(self, bar: MarketBar) -> None:
        self.cancel_all()
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        if not self.pos:
            self.entry_up, self.entry_down = self.am.donchian(self.entry_window)

        self.exit_up, self.exit_down = self.am.donchian(self.exit_window)
        if not self.pos:
            self.atr_value = self.am.atr(self.atr_window)
            self.long_entry = 0
            self.short_entry = 0
            self.long_stop = 0
            self.short_stop = 0
            self.send_buy_orders(self.entry_up)
            self.send_short_orders(self.entry_down)
        elif self.pos > 0:
            self.send_buy_orders(self.entry_up)
            sell_price = max(self.long_stop, self.exit_down)
            self.sell(sell_price, abs(self.pos), stop=True)
        elif self.pos < 0:
            self.send_short_orders(self.entry_down)
            cover_price = min(self.short_stop, self.exit_up)
            self.cover(cover_price, abs(self.pos), stop=True)

    def on_trade(self, trade: TradeRecord) -> None:
        if trade.direction == "long":
            self.long_entry = trade.price
            self.long_stop = self.long_entry - 2 * self.atr_value
        else:
            self.short_entry = trade.price
            self.short_stop = self.short_entry + 2 * self.atr_value

    def send_buy_orders(self, price: float) -> None:
        t = self.pos / self.fixed_size if self.fixed_size else 0
        if t < 1:
            self.buy(price, self.fixed_size, stop=True)
        if t < 2:
            self.buy(price + self.atr_value * 0.5, self.fixed_size, stop=True)
        if t < 3:
            self.buy(price + self.atr_value, self.fixed_size, stop=True)
        if t < 4:
            self.buy(price + self.atr_value * 1.5, self.fixed_size, stop=True)

    def send_short_orders(self, price: float) -> None:
        t = self.pos / self.fixed_size if self.fixed_size else 0
        if t > -1:
            self.short(price, self.fixed_size, stop=True)
        if t > -2:
            self.short(price - self.atr_value * 0.5, self.fixed_size, stop=True)
        if t > -3:
            self.short(price - self.atr_value, self.fixed_size, stop=True)
        if t > -4:
            self.short(price - self.atr_value * 1.5, self.fixed_size, stop=True)


class TrendRsiLongStrategy(CtaTemplate):
    author = "Codex"
    fast_window = 5
    slow_window = 20
    trend_window = 60
    rsi_window = 14
    rsi_entry = 52
    rsi_exit = 45
    fixed_size = 1
    stop_loss_percent = 8.0
    trailing_percent = 12.0

    fast_ma = 0.0
    slow_ma = 0.0
    trend_ma = 0.0
    rsi_value = 0.0
    entry_price = 0.0
    intra_trade_high = 0.0

    parameters = [
        "fast_window",
        "slow_window",
        "trend_window",
        "rsi_window",
        "rsi_entry",
        "rsi_exit",
        "fixed_size",
        "stop_loss_percent",
        "trailing_percent",
    ]
    variables = ["fast_ma", "slow_ma", "trend_ma", "rsi_value", "entry_price", "intra_trade_high"]

    def on_init(self) -> None:
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager(size=max(self.trend_window, self.slow_window, self.rsi_window) + 10)
        self.load_bar(10)

    def on_bar(self, bar: MarketBar) -> None:
        self.cancel_all()
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        fast_array = self.am.sma(self.fast_window, array=True)
        slow_array = self.am.sma(self.slow_window, array=True)
        self.fast_ma = float(fast_array[-1])
        self.slow_ma = float(slow_array[-1])
        self.trend_ma = self.am.sma(self.trend_window)
        self.rsi_value = self.am.rsi(self.rsi_window)

        fast_above_slow = self.fast_ma > self.slow_ma
        fast_was_below = float(fast_array[-2]) <= float(slow_array[-2])
        trend_ok = bar.close_price > self.trend_ma
        momentum_ok = self.rsi_value >= self.rsi_entry

        if self.pos == 0:
            self.entry_price = 0.0
            self.intra_trade_high = 0.0
            if fast_above_slow and fast_was_below and trend_ok and momentum_ok:
                self.buy(bar.close_price, self.fixed_size)
        elif self.pos > 0:
            if not self.entry_price:
                self.entry_price = bar.close_price
            self.intra_trade_high = max(self.intra_trade_high, bar.high_price, self.entry_price)
            stop_loss_price = self.entry_price * (1 - self.stop_loss_percent / 100)
            trailing_stop_price = self.intra_trade_high * (1 - self.trailing_percent / 100)
            weak_trend = self.fast_ma < self.slow_ma or self.rsi_value <= self.rsi_exit
            if bar.close_price <= stop_loss_price or bar.close_price <= trailing_stop_price or weak_trend:
                self.sell(bar.close_price, abs(self.pos))

    def on_trade(self, trade: TradeRecord) -> None:
        if self.pos > 0 and not self.entry_price:
            self.entry_price = trade.price
            self.intra_trade_high = trade.price
