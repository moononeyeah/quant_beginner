from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from config import DEFAULT_FEE_RATE, DEFAULT_INITIAL_CASH, DEFAULT_SLIPPAGE, default_end_date
from main import run_pipeline
from src.plotter import plot_equity_curve, plot_performance_dashboard, plot_price_with_signals
from src.strategies import STRATEGY_SPECS, get_strategy_parameter_table, get_strategy_source, get_strategy_spec
from src.utils import format_percent

st.set_page_config(page_title="单标回测", page_icon="📊", layout="wide")

st.title("📊 单标回测")

# ────────────────────────────── 侧边栏参数 ──────────────────────────────
with st.sidebar:
    st.header("⚙️ 回测配置")

    strategy_key = st.selectbox(
        "选择策略",
        options=list(STRATEGY_SPECS.keys()),
        format_func=lambda k: f"{STRATEGY_SPECS[k].display_name} ({k})",
        index=0,
    )
    spec = get_strategy_spec(strategy_key)

    symbol = st.text_input("交易代码", value="510300", help="例如 510300 或 000001")

    if spec.engine_type == "portfolio":
        st.warning("组合策略请在「组合回测」页面使用")
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

    # 策略参数编辑
    st.markdown("---")
    st.subheader("🔧 策略参数")
    default_params = spec.default_parameters
    param_df = get_strategy_parameter_table(strategy_key)

    # 用 data_editor 编辑参数
    edited_params: dict[str, Any] = {}
    for name, default_value in default_params.items():
        if isinstance(default_value, bool):
            edited_params[name] = st.toggle(name, value=default_value, help=param_df[param_df["参数名"] == name]["中文解释"].values[0] if not param_df.empty else "")
        elif isinstance(default_value, int):
            edited_params[name] = st.number_input(name, value=default_value, step=1, format="%d", help=param_df[param_df["参数名"] == name]["中文解释"].values[0] if not param_df.empty else "")
        elif isinstance(default_value, float):
            edited_params[name] = st.number_input(name, value=default_value, step=0.1, format="%.4f", help=param_df[param_df["参数名"] == name]["中文解释"].values[0] if not param_df.empty else "")
        else:
            edited_params[name] = st.text_input(name, value=str(default_value), help=param_df[param_df["参数名"] == name]["中文解释"].values[0] if not param_df.empty else "")

    run_btn = st.button("🚀 开始回测", type="primary", use_container_width=True)


# ────────────────────────────── 主区域 ──────────────────────────────
if run_btn:
    if spec.engine_type == "portfolio":
        st.error("组合策略请在「组合回测」页面使用")
        st.stop()

    with st.spinner("正在获取数据并运行回测..."):
        try:
            _, result, price_plot_path, equity_plot_path, debug_df, symbol_label = run_pipeline(
                symbol=symbol,
                start=start,
                end=end,
                initial_cash=initial_cash,
                fee_rate=fee_rate,
                slippage=slippage,
                frequency=frequency,
                strategy_name=strategy_key,
                strategy_params=edited_params,
            )
        except Exception as exc:
            st.error(f"回测失败：{exc}")
            st.stop()

    # 保存到 session state
    st.session_state["last_single_result"] = result
    st.session_state["last_single_symbol"] = symbol_label
    st.session_state["last_single_strategy"] = strategy_key
    st.session_state["last_single_context"] = {
        "start_date": start,
        "end_date": end,
        "frequency": frequency,
        "initial_cash": float(initial_cash),
        "fee_rate": float(fee_rate),
        "slippage": float(slippage),
        "strategy_params": edited_params,
    }

    st.success("回测完成！")

# 展示结果
if "last_single_result" in st.session_state:
    result = st.session_state["last_single_result"]
    symbol_label = st.session_state["last_single_symbol"]
    strategy_key = st.session_state["last_single_strategy"]
    spec = get_strategy_spec(strategy_key)

    # 总览卡片
    st.markdown("---")
    cols = st.columns(4)
    with cols[0]:
        st.metric("总收益率", format_percent(result.total_return))
    with cols[1]:
        st.metric("最大回撤", format_percent(result.max_drawdown))
    with cols[2]:
        st.metric("Sharpe", f"{result.statistics.get('sharpe_ratio', 0):.2f}")
    with cols[3]:
        st.metric("交易次数", result.trade_count)

    cols2 = st.columns(4)
    with cols2[0]:
        st.metric("年化收益", format_percent(result.statistics.get('annual_return', 0)))
    with cols2[1]:
        st.metric("Sortino", f"{result.statistics.get('sortino_ratio', 0):.2f}")
    with cols2[2]:
        st.metric("Calmar", f"{result.statistics.get('calmar_ratio', 0):.2f}")
    with cols2[3]:
        st.metric("盈亏比", f"{result.statistics.get('profit_loss_ratio', 0):.2f}")

    # Tabs
    tab_overview, tab_stats, tab_trades, tab_daily, tab_debug, tab_logs = st.tabs(
        ["📈 业绩图表", "📋 统计指标", "📝 成交记录", "📅 每日盈亏", "🔍 策略输出", "📜 运行日志"]
    )

    with tab_overview:
        col_left, col_right = st.columns(2)
        with col_left:
            if not result.equity_curve.empty:
                fig = plot_performance_dashboard(result.daily_results)
                st.pyplot(fig)
        with col_right:
            if not result.equity_curve.empty:
                st.line_chart(result.equity_curve.set_index("date")["equity"], use_container_width=True)

    with tab_stats:
        stats = result.statistics
        priority = [
            "total_return", "annual_return", "max_drawdown", "max_ddpercent",
            "sharpe_ratio", "sortino_ratio", "calmar_ratio", "return_drawdown_ratio",
            "win_rate", "profit_loss_ratio", "day_win_rate", "month_win_rate",
            "total_days", "profit_days", "loss_days",
            "total_trade_count", "max_drawdown_duration",
            "annual_volatility", "daily_volatility",
            "skewness", "kurtosis", "var_95", "cvar_95",
        ]
        rows = []
        seen = set()
        for key in priority:
            if key in stats and key not in seen:
                rows.append({"指标": key, "数值": stats[key]})
                seen.add(key)
        for key, val in stats.items():
            if key not in seen:
                rows.append({"指标": key, "数值": val})
                seen.add(key)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab_trades:
        if not result.trades.empty:
            st.dataframe(result.trades, use_container_width=True, hide_index=True)
        else:
            st.info("无成交记录")

    with tab_daily:
        if not result.daily_results.empty:
            st.dataframe(result.daily_results, use_container_width=True, hide_index=True)
        else:
            st.info("无每日盈亏数据")

    with tab_debug:
        if not result.strategy_output.empty:
            st.dataframe(result.strategy_output, use_container_width=True, hide_index=True)
        else:
            st.info("无策略输出")

    with tab_logs:
        if result.logs:
            st.text_area("日志", value="\n".join(result.logs), height=400)
        else:
            st.info("无日志")
