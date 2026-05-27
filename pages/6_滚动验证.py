from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd
import streamlit as st

from config import DEFAULT_FEE_RATE, DEFAULT_INITIAL_CASH, DEFAULT_SLIPPAGE, default_end_date
from src.backtest import run_strategy_backtest
from src.data_fetcher import fetch_daily_data
from src.optimizer import optimize_strategy
from src.strategies import STRATEGY_SPECS, get_strategy_spec
from src.utils import format_percent

st.set_page_config(page_title="滚动验证", page_icon="🧪", layout="wide")
st.title("🧪 Walk-Forward 滚动验证")

with st.sidebar:
    cta_keys = [k for k, v in STRATEGY_SPECS.items() if v.engine_type == "cta"]
    strategy_key = st.selectbox("策略", options=cta_keys, index=0)
    spec = get_strategy_spec(strategy_key)
    symbol = st.text_input("代码", value="510300")
    start = st.text_input("开始日期", value="20200101")
    end = st.text_input("结束日期", value=default_end_date())
    initial_cash = st.number_input("初始资金", value=DEFAULT_INITIAL_CASH, step=10000.0, format="%.2f")
    fee_rate = st.number_input("手续费率", value=DEFAULT_FEE_RATE, step=0.0001, format="%.6f")
    slippage = st.number_input("滑点", value=DEFAULT_SLIPPAGE, step=0.0001, format="%.6f")
    train_days = st.number_input("训练窗口(交易日)", value=120, step=20, min_value=40)
    test_days = st.number_input("验证窗口(交易日)", value=40, step=10, min_value=10)
    step_days = st.number_input("滚动步长(交易日)", value=20, step=5, min_value=5)
    st.markdown("---")
    st.caption("基础参数")
    base_params: dict[str, Any] = {}
    for name, val in spec.default_parameters.items():
        if isinstance(val, bool):
            base_params[name] = st.toggle(name, value=val)
        elif isinstance(val, int):
            base_params[name] = st.number_input(name, value=val, step=1, format="%d")
        elif isinstance(val, float):
            base_params[name] = st.number_input(name, value=val, step=0.1, format="%.4f")
        else:
            base_params[name] = st.text_input(name, value=str(val))
    run_btn = st.button("开始滚动验证", type="primary", use_container_width=True)

st.markdown("### 优化参数网格")
grid: dict[str, list[Any]] = {}
for name, val in spec.default_parameters.items():
    if isinstance(val, bool) or isinstance(val, str):
        continue
    txt = st.text_input(f"{name} 网格", value="", placeholder="例如 5,10,20", key=f"wf_{name}")
    if txt.strip():
        if isinstance(val, int):
            grid[name] = [int(x.strip()) for x in txt.split(",") if x.strip()]
        else:
            grid[name] = [float(x.strip()) for x in txt.split(",") if x.strip()]

if run_btn:
    if not grid:
        st.error("请至少设置一个优化参数网格")
        st.stop()
    with st.spinner("加载数据中..."):
        data = fetch_daily_data(symbol=symbol, start_date=start, end_date=end, frequency="daily")
        data = data.copy().sort_values("date").reset_index(drop=True)
    n = len(data)
    rows: list[dict[str, Any]] = []
    idx = 0
    pbar = st.progress(0.0)
    while idx + train_days + test_days <= n:
        train_df = data.iloc[idx: idx + train_days].copy()
        test_df = data.iloc[idx + train_days: idx + train_days + test_days].copy()
        if train_df.empty or test_df.empty:
            break
        opt_df = optimize_strategy(
            data=train_df.assign(symbol=symbol),
            strategy_name=strategy_key,
            base_setting=base_params,
            optimization_grid=grid,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage=slippage,
            use_parallel=True,
        )
        if opt_df.empty:
            idx += step_days
            continue
        best = opt_df.iloc[0].to_dict()
        best_params = {k: best.get(k, base_params.get(k)) for k in spec.default_parameters.keys()}
        test_result = run_strategy_backtest(
            data=test_df.assign(symbol=symbol),
            strategy_name=strategy_key,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage=slippage,
            strategy_setting=best_params,
        )
        rows.append(
            {
                "train_start": str(pd.to_datetime(train_df["date"].iloc[0]).date()),
                "train_end": str(pd.to_datetime(train_df["date"].iloc[-1]).date()),
                "test_start": str(pd.to_datetime(test_df["date"].iloc[0]).date()),
                "test_end": str(pd.to_datetime(test_df["date"].iloc[-1]).date()),
                "test_return": test_result.total_return,
                "test_max_dd": test_result.max_drawdown,
                "test_sharpe": test_result.statistics.get("sharpe_ratio", 0.0),
                "best_params": best_params,
            }
        )
        idx += step_days
        pbar.progress(min((idx + train_days + test_days) / n, 1.0))

    wf_df = pd.DataFrame(rows)
    st.session_state["wf_result_df"] = wf_df
    st.success(f"完成 {len(wf_df)} 个滚动窗口")

if "wf_result_df" in st.session_state:
    wf_df = st.session_state["wf_result_df"]
    if wf_df.empty:
        st.info("无结果")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("窗口数", len(wf_df))
        c2.metric("平均验证收益", format_percent(wf_df["test_return"].mean()))
        c3.metric("平均验证Sharpe", f"{wf_df['test_sharpe'].mean():.2f}")
        st.dataframe(wf_df, use_container_width=True, hide_index=True)
        st.line_chart(wf_df[["test_return", "test_sharpe"]], use_container_width=True)
