from __future__ import annotations

import os
from pathlib import Path

from config import BASE_DIR, OUTPUT_DIR

# 把 matplotlib/fontconfig 缓存放到项目内可写目录，避免启动时反复告警。
PLOT_CACHE_DIR = BASE_DIR / ".cache" / "matplotlib"
PLOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(PLOT_CACHE_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(BASE_DIR / ".cache"))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.utils import ensure_dir


def _setup_chinese_font() -> None:
    """设置中文字体候选，尽量避免图表中文乱码。"""
    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def plot_price_with_signals(df: pd.DataFrame, symbol: str, output_dir: Path = OUTPUT_DIR) -> Path:
    """绘制收盘价、MA5、MA20 以及买卖点，并保存图片。"""
    if df.empty:
        raise ValueError("无法画图：数据为空")
    ensure_dir(output_dir)
    _setup_chinese_font()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df["date"], df["close"], label="收盘价", linewidth=1.4)
    ax.plot(df["date"], df["ma5"], label="MA5", linewidth=1.0)
    ax.plot(df["date"], df["ma20"], label="MA20", linewidth=1.0)

    buys = df[df["signal"] == 1]
    sells = df[df["signal"] == -1]
    ax.scatter(buys["date"], buys["close"], marker="^", color="red", label="买入", s=70)
    ax.scatter(sells["date"], sells["close"], marker="v", color="green", label="卖出", s=70)
    ax.set_title(f"{symbol} 收盘价与双均线信号")
    ax.set_xlabel("日期")
    ax.set_ylabel("价格")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    path = output_dir / f"{symbol}_price_signal.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_equity_curve(equity_curve: pd.DataFrame, symbol: str, output_dir: Path = OUTPUT_DIR) -> Path:
    """绘制资金曲线，并保存图片。"""
    if equity_curve.empty:
        raise ValueError("无法画图：资金曲线为空")
    ensure_dir(output_dir)
    _setup_chinese_font()

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(equity_curve["date"], equity_curve["equity"], label="资金曲线", color="#1f77b4")
    ax.set_title(f"{symbol} 回测资金曲线")
    ax.set_xlabel("日期")
    ax.set_ylabel("资金")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    path = output_dir / f"{symbol}_equity_curve.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_rotation_selection(selection: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> Path:
    """绘制 ETF 轮动调仓记录，展示每次持有目标。"""
    if selection.empty:
        raise ValueError("无法画图：轮动调仓记录为空")
    ensure_dir(output_dir)
    _setup_chinese_font()

    filtered = selection.copy()
    filtered["signal_date"] = pd.to_datetime(filtered["signal_date"])
    symbols = list(dict.fromkeys(filtered["target_symbol"].astype(str).tolist()))
    symbol_to_y = {symbol: idx for idx, symbol in enumerate(symbols)}
    filtered["target_y"] = filtered["target_symbol"].map(symbol_to_y)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.step(filtered["signal_date"], filtered["target_y"], where="post", linewidth=1.6, color="#ff7f0e")
    ax.scatter(filtered["signal_date"], filtered["target_y"], s=40, color="#d62728")
    ax.set_title("ETF 轮动调仓记录")
    ax.set_xlabel("日期")
    ax.set_ylabel("持有 ETF")
    ax.set_yticks(list(symbol_to_y.values()))
    ax.set_yticklabels(list(symbol_to_y.keys()))
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()

    path = output_dir / "etf_rotation_selection.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_performance_dashboard(daily_results: pd.DataFrame):
    """绘制接近 vn.py 回测面板的四宫格业绩图。"""
    if daily_results.empty:
        raise ValueError("无法画图：日度结果为空")

    _setup_chinese_font()
    df = daily_results.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["highlevel"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] - df["highlevel"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))

    axes[0, 0].plot(df["date"], df["equity"], color="#2563eb", linewidth=1.6)
    axes[0, 0].set_title("账户净值")
    axes[0, 0].grid(alpha=0.2)

    axes[0, 1].fill_between(df["date"], df["drawdown"], 0, color="#dc2626", alpha=0.65)
    axes[0, 1].set_title("净值回撤")
    axes[0, 1].grid(alpha=0.2)

    axes[1, 0].bar(df["date"], df["net_pnl"], color=np.where(df["net_pnl"] >= 0, "#16a34a", "#dc2626"))
    axes[1, 0].set_title("每日盈亏")
    axes[1, 0].grid(alpha=0.2)

    axes[1, 1].hist(df["net_pnl"], bins=min(40, max(10, len(df) // 3)), color="#7c3aed", alpha=0.8)
    axes[1, 1].set_title("盈亏分布")
    axes[1, 1].grid(alpha=0.2)

    for axis in axes[0]:
        axis.tick_params(axis="x", rotation=20)
    axes[1, 0].tick_params(axis="x", rotation=20)

    fig.tight_layout()
    return fig
