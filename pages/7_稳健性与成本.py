from __future__ import annotations

from copy import deepcopy
from typing import Any

import pandas as pd
import streamlit as st

from config import DEFAULT_FEE_RATE, DEFAULT_INITIAL_CASH, DEFAULT_SLIPPAGE, default_end_date
from src.backtest import run_strategy_backtest
from src.data_fetcher import fetch_daily_data
from src.strategies import STRATEGY_SPECS, get_strategy_spec
from src.utils import format_percent

st.set_page_config(page_title="稳健性与成本", page_icon="🛡️", layout="wide")
st.title("🛡️ 稳健性与成本压力测试")

with st.sidebar:
    cta_keys = [k for k, v in STRATEGY_SPECS.items() if v.engine_type == "cta"]
    strategy_key = st.selectbox("策略", options=cta_keys, index=0)
    spec = get_strategy_spec(strategy_key)
    symbol = st.text_input("代码", value="510300")
    frequency = st.selectbox("周期", options=["daily", "1", "5", "15", "30", "60"], index=0)
    start = st.text_input("开始", value="20230101")
    end = st.text_input("结束", value=default_end_date())
    initial_cash = st.number_input("初始资金", value=DEFAULT_INITIAL_CASH, step=10000.0)
    fee_rate = st.number_input("基础手续费率", value=DEFAULT_FEE_RATE, step=0.0001, format="%.6f")
    slippage = st.number_input("基础滑点", value=DEFAULT_SLIPPAGE, step=0.0001, format="%.6f")
    perturb_pct = st.number_input("参数扰动比例", value=0.1, step=0.05, min_value=0.01, max_value=0.5)
    shift_days = st.number_input("日期扰动天数", value=20, step=5, min_value=1)
    run_btn = st.button("开始测试", type="primary", use_container_width=True)

st.markdown("### 参数设置")
base_params: dict[str, Any] = {}
for k, v in spec.default_parameters.items():
    if isinstance(v, bool):
        base_params[k] = st.toggle(k, value=v)
    elif isinstance(v, int):
        base_params[k] = st.number_input(k, value=v, step=1, format="%d")
    elif isinstance(v, float):
        base_params[k] = st.number_input(k, value=v, step=0.1, format="%.4f")
    else:
        base_params[k] = st.text_input(k, value=str(v))


def _run_case(
    data: pd.DataFrame,
    params: dict[str, Any],
    fee: float,
    slip: float,
) -> dict[str, Any]:
    result = run_strategy_backtest(
        data=data.assign(symbol=symbol),
        strategy_name=strategy_key,
        initial_cash=initial_cash,
        fee_rate=fee,
        slippage=slip,
        strategy_setting=params,
    )
    return {
        "total_return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "sharpe": result.statistics.get("sharpe_ratio", 0.0),
    }


if run_btn:
    with st.spinner("加载数据并运行压力测试..."):
        data = fetch_daily_data(symbol=symbol, start_date=start, end_date=end, frequency=frequency)
        base = _run_case(data, base_params, fee_rate, slippage)
        rows: list[dict[str, Any]] = [{"case": "base", **base}]

        # 参数扰动
        for key, value in base_params.items():
            if isinstance(value, (bool, str)):
                continue
            for sign in (-1, 1):
                p = deepcopy(base_params)
                if isinstance(value, int):
                    p[key] = max(1, int(round(value * (1 + sign * perturb_pct))))
                else:
                    p[key] = float(value) * (1 + sign * perturb_pct)
                metric = _run_case(data, p, fee_rate, slippage)
                rows.append({"case": f"param:{key}:{'down' if sign < 0 else 'up'}", **metric})

        # 日期扰动
        s = pd.to_datetime(start)
        e = pd.to_datetime(end)
        shifts = [(-shift_days, -shift_days), (shift_days, shift_days)]
        for a, b in shifts:
            s2 = (s + pd.Timedelta(days=a))
            e2 = (e + pd.Timedelta(days=b))
            if frequency == "daily":
                ss = s2.strftime("%Y%m%d")
                ee = e2.strftime("%Y%m%d")
            else:
                ss = s2.strftime("%Y-%m-%d %H:%M:%S")
                ee = e2.strftime("%Y-%m-%d %H:%M:%S")
            try:
                d2 = fetch_daily_data(symbol=symbol, start_date=ss, end_date=ee, frequency=frequency)
                metric = _run_case(d2, base_params, fee_rate, slippage)
                rows.append({"case": f"time_shift:{a}", **metric})
            except Exception:
                pass

        # 成本压力
        for m in [0.5, 1.0, 2.0, 3.0]:
            metric = _run_case(data, base_params, fee_rate * m, slippage * m)
            rows.append({"case": f"cost_x{m}", **metric})

    df = pd.DataFrame(rows)
    st.session_state["robust_cost_df"] = df
    st.success("测试完成")

if "robust_cost_df" in st.session_state:
    df = st.session_state["robust_cost_df"]
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        base_row = df[df["case"] == "base"].iloc[0]
        stability = 1.0 - min(
            1.0,
            (df["total_return"].std(ddof=0) / (abs(base_row["total_return"]) + 1e-6))
        )
        st.metric("稳定性评分(0-1)", f"{max(0.0, stability):.2f}")
        st.line_chart(df.set_index("case")[["total_return", "sharpe"]], use_container_width=True)
