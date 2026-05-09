from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

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
