from __future__ import annotations

import numpy as np
import pandas as pd

from config import MA_WINDOWS


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算均线、涨跌幅、成交量均线和简化 RSI，返回新的 DataFrame。"""
    if df.empty:
        raise ValueError("无法计算指标：行情数据为空")

    result = df.copy()
    for window in MA_WINDOWS:
        result[f"ma{window}"] = result["close"].rolling(window=window, min_periods=1).mean()

    result["pct_change"] = result["close"].pct_change().fillna(0.0)
    result["volume_ma5"] = result["volume"].rolling(window=5, min_periods=1).mean()
    result["rsi"] = calculate_rsi(result["close"], window=14)
    return result


def calculate_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """使用常见的平均涨跌幅方法计算简化版 RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)
