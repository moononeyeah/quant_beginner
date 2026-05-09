from __future__ import annotations

from typing import Iterable

import pandas as pd

from config import DEFAULT_ROTATION_LOOKBACK_DAYS, DEFAULT_ROTATION_SYMBOLS
from src.data_fetcher import fetch_daily_data


def parse_rotation_symbols(symbols: str | Iterable[str] | None) -> list[str]:
    """解析 ETF 轮动代码列表；为空时返回默认 ETF 池。"""
    if symbols is None:
        return DEFAULT_ROTATION_SYMBOLS.copy()
    if isinstance(symbols, str):
        parsed = [item.strip() for item in symbols.replace("，", ",").split(",") if item.strip()]
    else:
        parsed = [str(item).strip() for item in symbols if str(item).strip()]
    if not parsed:
        return DEFAULT_ROTATION_SYMBOLS.copy()
    deduped: list[str] = []
    seen: set[str] = set()
    for symbol in parsed:
        if symbol not in seen:
            deduped.append(symbol)
            seen.add(symbol)
    return deduped


def fetch_rotation_data(symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    """抓取 ETF 池的历史日线数据，并合并成统一表结构。"""
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        df = fetch_daily_data(symbol=symbol, start_date=start_date, end_date=end_date, frequency="daily")
        item = df.copy()
        item["symbol"] = symbol
        frames.append(item)
    if not frames:
        raise ValueError("ETF 池为空，无法运行轮动策略")
    merged = pd.concat(frames, ignore_index=True)
    return merged.sort_values(["date", "symbol"]).reset_index(drop=True)


def generate_rotation_plan(
    price_data: pd.DataFrame,
    lookback_days: int = DEFAULT_ROTATION_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """按近 N 日涨幅排名，在每月最后一个交易日生成下月调仓计划。"""
    if price_data.empty:
        raise ValueError("轮动策略无法生成计划：行情数据为空")
    if lookback_days <= 0:
        raise ValueError("lookback_days 必须大于 0")

    required = {"date", "symbol", "close"}
    if not required.issubset(price_data.columns):
        raise ValueError(f"轮动策略缺少必要字段：{sorted(required - set(price_data.columns))}")

    close_panel = (
        price_data.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
        .sort_index()
        .astype(float)
    )
    momentum = close_panel / close_panel.shift(lookback_days) - 1
    calendar = close_panel.index.to_series().sort_values()
    month_ends = calendar.groupby(calendar.dt.to_period("M")).max().tolist()

    plans: list[dict] = []
    for signal_date in month_ends:
        scores = momentum.loc[signal_date].dropna().sort_values(ascending=False)
        if scores.empty:
            continue
        loc = close_panel.index.get_loc(signal_date)
        if loc >= len(close_panel.index) - 1:
            continue
        execute_date = close_panel.index[loc + 1]
        ranking = " | ".join(f"{symbol}:{value:.2%}" for symbol, value in scores.items())
        plans.append(
            {
                "signal_date": pd.Timestamp(signal_date),
                "execute_date": pd.Timestamp(execute_date),
                "target_symbol": str(scores.index[0]),
                "target_return": float(scores.iloc[0]),
                "ranking": ranking,
            }
        )

    if not plans:
        raise ValueError(
            f"轮动策略没有生成可执行调仓计划；请检查日期区间，至少要覆盖 {lookback_days} 个交易日以上"
        )

    return pd.DataFrame(plans).sort_values("execute_date").reset_index(drop=True)
