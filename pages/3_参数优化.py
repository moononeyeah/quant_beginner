from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from config import DEFAULT_FEE_RATE, DEFAULT_INITIAL_CASH, DEFAULT_SLIPPAGE, default_end_date
from src.data_fetcher import fetch_daily_data
from src.optimizer import optimize_strategy_parallel
from src.strategies import STRATEGY_SPECS, get_strategy_spec
from src.utils import format_percent

st.set_page_config(page_title="参数优化", page_icon="⚙️", layout="wide")

st.title("⚙️ 参数优化")

# ────────────────────────────── 侧边栏参数 ──────────────────────────────
with st.sidebar:
    st.header("⚙️ 优化配置")

    strategy_key = st.selectbox(
        "选择策略",
        options=list(STRATEGY_SPECS.keys()),
        format_func=lambda k: f"{STRATEGY_SPECS[k].display_name} ({k})",
        index=0,
    )
    spec = get_strategy_spec(strategy_key)

    symbol = st.text_input("交易代码", value="510300")

    if spec.engine_type == "portfolio":
        st.warning("组合策略暂不支持参数优化")
        frequency = "daily"
    else:
        frequency = st.selectbox("K线周期", ["daily", "1", "5", "15", "30", "60"], index=0)

    col1, col2 = st.columns(2)
    with col1:
        start = st.text_input("开始日期", value="20230101")
    with col2:
        end = st.text_input("结束日期", value=default_end_date())

    initial_cash = st.number_input("初始资金", value=DEFAULT_INITIAL_CASH, step=10000.0, format="%.2f")
    fee_rate = st.number_input("手续费率", value=DEFAULT_FEE_RATE, step=0.0001, format="%.6f")
    slippage = st.number_input("滑点", value=DEFAULT_SLIPPAGE, step=0.0001, format="%.6f")

    use_parallel = st.toggle("使用多进程并行", value=True)
    max_workers = st.number_input("最大进程数", value=0, step=1, help="0 表示自动（CPU核心数-1）")

    # 基础参数
    st.markdown("---")
    st.subheader("🔧 基础参数")
    default_params = spec.default_parameters
    base_params: dict[str, Any] = {}
    for name, default_value in default_params.items():
        if isinstance(default_value, bool):
            base_params[name] = st.toggle(f"{name} (基础)", value=default_value)
        elif isinstance(default_value, int):
            base_params[name] = st.number_input(f"{name} (基础)", value=default_value, step=1, format="%d")
        elif isinstance(default_value, float):
            base_params[name] = st.number_input(f"{name} (基础)", value=default_value, step=0.1, format="%.4f")
        else:
            base_params[name] = st.text_input(f"{name} (基础)", value=str(default_value))

    run_btn = st.button("🚀 开始优化", type="primary", use_container_width=True)


# ────────────────────────────── 主区域：优化网格配置 ──────────────────────────────
st.markdown("### 优化参数网格")
st.info("为每个要优化的参数设置取值列表。不参与优化的参数使用上方「基础参数」的值。")

grid_config: dict[str, list[Any]] = {}
cols = st.columns(min(3, max(len(default_params), 1)))
for idx, (name, default_value) in enumerate(default_params.items()):
    with cols[idx % len(cols)]:
        if isinstance(default_value, bool):
            st.markdown(f"**{name}** (bool，暂不支持优化)")
        elif isinstance(default_value, int):
            val_str = st.text_input(
                f"{name} 取值列表",
                value="",
                placeholder="例如: 5,10,20",
                key=f"grid_{name}",
            )
            if val_str.strip():
                try:
                    grid_config[name] = [int(x.strip()) for x in val_str.split(",")]
                except ValueError:
                    st.error(f"{name} 必须是整数列表")
        elif isinstance(default_value, float):
            val_str = st.text_input(
                f"{name} 取值列表",
                value="",
                placeholder="例如: 0.5,1.0,1.5",
                key=f"grid_{name}",
            )
            if val_str.strip():
                try:
                    grid_config[name] = [float(x.strip()) for x in val_str.split(",")]
                except ValueError:
                    st.error(f"{name} 必须是数字列表")
        else:
            st.markdown(f"**{name}** (str，暂不支持优化)")

# 计算组合数
total_combinations = 1
for vals in grid_config.values():
    total_combinations *= len(vals)

if grid_config:
    st.markdown(f"**预计参数组合数：{total_combinations}**")
    if total_combinations > 5000:
        st.error("组合数超过 5000，请缩小优化范围")
    elif total_combinations > 500:
        st.warning("组合数较多，优化可能需要一些时间")


# ────────────────────────────── 运行优化 ──────────────────────────────
if run_btn:
    if spec.engine_type == "portfolio":
        st.error("组合策略暂不支持参数优化")
        st.stop()

    if not grid_config:
        st.error("请至少设置一个优化参数")
        st.stop()

    if total_combinations > 5000:
        st.error("组合数超过 5000，请缩小优化范围")
        st.stop()

    progress_bar = st.progress(0.0)
    status_text = st.empty()

    def on_progress(completed: int, total: int) -> None:
        progress_bar.progress(completed / total)
        status_text.text(f"进度：{completed}/{total}")

    with st.spinner("正在获取数据并运行参数优化..."):
        try:
            # 先获取数据
            data = fetch_daily_data(symbol=symbol, start_date=start, end_date=end, frequency=frequency)

            result = optimize_strategy_parallel(
                data=data,
                strategy_name=strategy_key,
                base_setting=base_params,
                optimization_grid=grid_config,
                initial_cash=initial_cash,
                fee_rate=fee_rate,
                slippage=slippage,
                max_workers=max_workers if max_workers > 0 else None,
                progress_callback=on_progress,
            )
        except Exception as exc:
            st.error(f"优化失败：{exc}")
            st.stop()

    st.session_state["last_opt_result"] = result
    st.success("优化完成！")

# 展示结果
if "last_opt_result" in st.session_state:
    result = st.session_state["last_opt_result"]
    df = result.results_df

    st.markdown("---")
    st.subheader("📊 优化结果")

    if not df.empty:
        # 排序目标列
        target_cols = ["total_return", "sharpe_ratio", "sortino_ratio", "calmar_ratio", "max_drawdown"]
        target_col = st.selectbox("排序指标", options=[c for c in target_cols if c in df.columns], index=0)
        ascending = st.toggle("升序", value=False)

        sorted_df = df.sort_values(target_col, ascending=ascending, na_position="last").reset_index(drop=True)
        st.dataframe(sorted_df, use_container_width=True, hide_index=True)

        # Top N 展示
        top_n = min(10, len(sorted_df))
        st.subheader(f"🏆 Top {top_n} 参数组合")
        top_df = sorted_df.head(top_n)

        # 关键指标对比图
        chart_cols = [c for c in ["total_return", "sharpe_ratio", "max_drawdown"] if c in top_df.columns]
        if chart_cols:
            st.bar_chart(top_df[chart_cols])
    else:
        st.info("无优化结果")
