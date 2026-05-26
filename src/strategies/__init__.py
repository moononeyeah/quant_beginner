from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from config import DEFAULT_ROTATION_LOOKBACK_DAYS
from src.strategy_base import CtaTemplate
from .cta_presets import (
    AtrRsiStrategy,
    BollChannelStrategy,
    DoubleMaStrategy,
    DualThrustStrategy,
    KingKeltnerStrategy,
    MultiSignalStrategy,
    MultiTimeframeStrategy,
    TestStrategy,
    TrendRsiLongStrategy,
    TurtleSignalStrategy,
)


@dataclass(frozen=True)
class StrategySpec:
    key: str
    display_name: str
    category: str
    engine_type: str
    description: str
    supports_frequency: str
    strategy_class: type[CtaTemplate] | None = None
    source_file: str = ""

    @property
    def default_parameters(self) -> dict[str, Any]:
        if self.strategy_class:
            return self.strategy_class.get_class_parameters()
        if self.key == "rotation":
            return {"lookback_days": DEFAULT_ROTATION_LOOKBACK_DAYS}
        return {}


def _source_file_of(strategy_class: type[CtaTemplate] | None) -> str:
    if not strategy_class:
        return ""
    return str(Path(inspect.getsourcefile(strategy_class) or "").resolve())


STRATEGY_SPECS: dict[str, StrategySpec] = {
    "double_ma": StrategySpec(
        key="double_ma",
        display_name="Double MA（vnpy）",
        category="CTA",
        engine_type="cta",
        description="vnpy 预制双均线策略，支持多空切换。",
        supports_frequency="daily/1/5/15/30/60",
        strategy_class=DoubleMaStrategy,
        source_file=_source_file_of(DoubleMaStrategy),
    ),
    "atr_rsi": StrategySpec(
        key="atr_rsi",
        display_name="ATR RSI（vnpy）",
        category="CTA",
        engine_type="cta",
        description="ATR 波动过滤 + RSI 方向判断 + 移动止损。",
        supports_frequency="daily/1/5/15/30/60",
        strategy_class=AtrRsiStrategy,
        source_file=_source_file_of(AtrRsiStrategy),
    ),
    "boll_channel": StrategySpec(
        key="boll_channel",
        display_name="Boll Channel（vnpy）",
        category="CTA",
        engine_type="cta",
        description="布林带 + CCI + ATR 止损的 15 分钟突破策略。",
        supports_frequency="1/5/15/30/60",
        strategy_class=BollChannelStrategy,
        source_file=_source_file_of(BollChannelStrategy),
    ),
    "dual_thrust": StrategySpec(
        key="dual_thrust",
        display_name="Dual Thrust（vnpy）",
        category="CTA",
        engine_type="cta",
        description="Dual Thrust 日内突破策略。",
        supports_frequency="1/5/15/30/60",
        strategy_class=DualThrustStrategy,
        source_file=_source_file_of(DualThrustStrategy),
    ),
    "king_keltner": StrategySpec(
        key="king_keltner",
        display_name="King Keltner（vnpy）",
        category="CTA",
        engine_type="cta",
        description="Keltner 通道 + OCO + 移动止盈。",
        supports_frequency="1/5/15/30/60",
        strategy_class=KingKeltnerStrategy,
        source_file=_source_file_of(KingKeltnerStrategy),
    ),
    "multi_signal": StrategySpec(
        key="multi_signal",
        display_name="Multi Signal（vnpy）",
        category="CTA",
        engine_type="cta",
        description="RSI、CCI、MA 三信号合成后的目标仓位策略。",
        supports_frequency="1/5/15/30/60",
        strategy_class=MultiSignalStrategy,
        source_file=_source_file_of(MultiSignalStrategy),
    ),
    "multi_timeframe": StrategySpec(
        key="multi_timeframe",
        display_name="Multi Timeframe（vnpy）",
        category="CTA",
        engine_type="cta",
        description="15 分钟趋势 + 5 分钟 RSI 触发的多周期策略。",
        supports_frequency="1/5/15/30/60",
        strategy_class=MultiTimeframeStrategy,
        source_file=_source_file_of(MultiTimeframeStrategy),
    ),
    "test_strategy": StrategySpec(
        key="test_strategy",
        display_name="Test Strategy（vnpy）",
        category="CTA",
        engine_type="cta",
        description="用于验证下单、撤单、停止单流程的测试策略。",
        supports_frequency="daily/1/5/15/30/60",
        strategy_class=TestStrategy,
        source_file=_source_file_of(TestStrategy),
    ),
    "trend_rsi_long": StrategySpec(
        key="trend_rsi_long",
        display_name="Trend RSI Long",
        category="CTA",
        engine_type="cta",
        description="项目内扩展的 long-only 趋势 RSI 策略。",
        supports_frequency="daily/1/5/15/30/60",
        strategy_class=TrendRsiLongStrategy,
        source_file=_source_file_of(TrendRsiLongStrategy),
    ),
    "turtle_signal": StrategySpec(
        key="turtle_signal",
        display_name="Turtle Signal（vnpy）",
        category="CTA",
        engine_type="cta",
        description="唐奇安通道 + ATR 金字塔加仓 + 出场通道。",
        supports_frequency="daily/1/5/15/30/60",
        strategy_class=TurtleSignalStrategy,
        source_file=_source_file_of(TurtleSignalStrategy),
    ),
    "rotation": StrategySpec(
        key="rotation",
        display_name="ETF Rotation",
        category="Portfolio",
        engine_type="portfolio",
        description="本地 ETF 动量轮动组合策略。",
        supports_frequency="daily",
    ),
}


PARAMETER_DESCRIPTIONS: dict[str, str] = {
    "symbol": "单标的回测代码。股票或 ETF 代码，例如 510300。",
    "rotation_symbols": "ETF 轮动池。轮动策略会在这些代码里选择近期表现最强的品种。",
    "frequency": "K 线周期。daily 表示日线，数字表示分钟线。",
    "start": "回测开始时间。日线使用 YYYYMMDD，分钟线使用 YYYY-MM-DD HH:MM:SS。",
    "end": "回测结束时间。格式与开始时间一致。",
    "initial_cash": "初始资金。用于计算资金曲线、收益率和仓位价值。",
    "fee_rate": "手续费率。0.0003 代表成交金额的万分之三。",
    "slippage": "滑点。模拟成交价格相对委托价格的不利偏移。",
    "atr_length": "ATR 计算窗口。数值越大，对波动变化越不敏感。",
    "atr_ma_length": "ATR 均线窗口。用于判断当前波动是否高于近期平均波动。",
    "rsi_length": "RSI 计算窗口。数值越小，动量信号越敏感。",
    "rsi_entry": "RSI 入场阈值偏移。买入阈值为 50 加该值，卖出阈值为 50 减该值。",
    "trailing_percent": "移动止损百分比。持仓盈利后，价格从高点或低点回撤超过该比例时止损。",
    "fixed_size": "每次下单数量。数值越大，单次交易仓位越重。",
    "boll_window": "布林带计算窗口。用于统计中轨和波动区间。",
    "boll_dev": "布林带标准差倍数。数值越大，突破条件越严格。",
    "cci_window": "CCI 计算窗口。用于判断价格偏离程度。",
    "atr_window": "ATR 波动窗口。用于计算止损距离或通道波动。",
    "sl_multiplier": "止损 ATR 倍数。数值越大，止损距离越宽。",
    "fast_window": "快均线窗口。数值越小，越快反映近期价格变化。",
    "slow_window": "慢均线窗口。数值越大，越偏向长期趋势。",
    "k1": "Dual Thrust 多头突破系数。数值越大，多头入场价越高。",
    "k2": "Dual Thrust 空头突破系数。数值越大，空头入场价越低。",
    "kk_length": "Keltner 通道窗口。用于计算通道中轴和波动范围。",
    "kk_dev": "Keltner 通道宽度倍数。数值越大，突破条件越严格。",
    "rsi_window": "RSI 计算窗口。用于衡量上涨和下跌动量强弱。",
    "rsi_level": "RSI 信号阈值。决定多空信号触发的强度要求。",
    "cci_level": "CCI 信号阈值。决定价格偏离达到多大才触发信号。",
    "rsi_signal": "RSI 信号偏移。买入阈值为 50 加该值，卖出阈值为 50 减该值。",
    "test_trigger": "测试策略触发间隔。每隔多少根 K 线执行一次测试动作。",
    "entry_window": "唐奇安入场通道窗口。突破该窗口高低点时尝试入场。",
    "exit_window": "唐奇安出场通道窗口。跌破或突破该窗口边界时离场。",
    "trend_window": "长期趋势均线窗口。价格高于该均线时才允许做多。",
    "rsi_exit": "RSI 离场阈值。RSI 转弱到该值附近时退出多头。",
    "stop_loss_percent": "固定止损百分比。价格相对入场价亏损超过该比例时离场。",
    "lookback_days": "轮动回看天数。策略比较最近 N 个交易日涨幅，选择涨幅最高的 ETF。",
}


def get_strategy_spec(strategy_key: str) -> StrategySpec:
    spec = STRATEGY_SPECS.get(strategy_key)
    if not spec:
        raise ValueError(f"未找到策略定义：{strategy_key}")
    return spec


def get_strategy_parameter_table(strategy_key: str) -> pd.DataFrame:
    spec = get_strategy_spec(strategy_key)
    rows = [
        {
            "参数名": name,
            "默认值": value,
            "类型": type(value).__name__,
            "中文解释": PARAMETER_DESCRIPTIONS.get(name, "策略参数。可结合策略源码理解具体用途。"),
        }
        for name, value in spec.default_parameters.items()
    ]
    return pd.DataFrame(rows)


def get_strategy_source(strategy_key: str) -> tuple[str, str]:
    spec = get_strategy_spec(strategy_key)
    if not spec.strategy_class:
        return spec.source_file, ""
    return spec.source_file, inspect.getsource(spec.strategy_class)


def list_strategy_catalog() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key, spec in STRATEGY_SPECS.items():
        rows.append(
            {
                "策略键": key,
                "显示名称": spec.display_name,
                "分类": spec.category,
                "引擎": spec.engine_type,
                "支持周期": spec.supports_frequency,
                "默认参数": spec.default_parameters,
                "源码文件": spec.source_file,
            }
        )
    return pd.DataFrame(rows)


def validate_strategy_parameters(strategy_key: str, params: dict[str, Any] | None) -> None:
    """校验策略参数，尽早阻断明显无效的配置。"""
    params = params or {}
    spec = get_strategy_spec(strategy_key)
    default_params = spec.default_parameters

    # 仅校验策略定义中声明的参数，避免外部扩展字段误报。
    invalid_numeric: list[str] = []
    for name, default_value in default_params.items():
        if not isinstance(default_value, (int, float)) or isinstance(default_value, bool):
            continue
        if name not in params:
            continue
        try:
            value = float(params[name])
        except Exception as exc:
            raise ValueError(f"参数 `{name}` 必须是数字，当前值：{params[name]}") from exc
        if value <= 0:
            invalid_numeric.append(name)
    if invalid_numeric:
        raise ValueError(f"以下参数必须大于 0：{invalid_numeric}")

    def _v(name: str, fallback: Any) -> Any:
        return params.get(name, fallback)

    # 常见窗口逻辑校验
    if "fast_window" in default_params and "slow_window" in default_params:
        fast_window = int(_v("fast_window", default_params["fast_window"]))
        slow_window = int(_v("slow_window", default_params["slow_window"]))
        if fast_window >= slow_window:
            raise ValueError("参数不合法：`fast_window` 必须小于 `slow_window`")

    if strategy_key == "turtle_signal":
        entry_window = int(_v("entry_window", default_params.get("entry_window", 20)))
        exit_window = int(_v("exit_window", default_params.get("exit_window", 10)))
        if entry_window <= exit_window:
            raise ValueError("参数不合法：`entry_window` 必须大于 `exit_window`")
