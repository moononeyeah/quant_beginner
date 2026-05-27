from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from config import DEFAULT_FEE_RATE, DEFAULT_INITIAL_CASH, DEFAULT_ROTATION_SYMBOLS, DEFAULT_SLIPPAGE, default_end_date
from main import run_portfolio_pipeline
from src.strategies import STRATEGY_SPECS, get_strategy_parameter_table, get_strategy_spec
from src.utils import format_percent

st.set_page_config(page_title="组合回测", page_icon="🏗️", layout="wide")

st.title("🏗️ 组合回测")

# ────────────────────────────── 侧边栏参数 ──────────────────────────────
with st.sidebar:
    st.header("⚙️ 组合配置")

    # 只显示 cta 类型策略
    cta_keys = [k for k, spec in STRATEGY_SPECS.items() if spec.engine_type == "cta"]
    strategy_key = st.selectbox(
        "选择策略",
        options=cta_keys,
        format_func=lambda k: f"{STRATEGY_SPECS[k].display_name} ({k})",
        index=0,
    )
    spec = get_strategy_spec(strategy_key)

    symbols_str = st.text_input(
        "标的池（逗号分隔）",
        value=",".join(DEFAULT_ROTATION_SYMBOLS),
        help="例如 510300,159915,512100",
    )
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]

    weights_json = st.text_area(
        "权重 JSON（留空则等权）",
        value="{}",
        help='例如 {"510300": 0.5, "159915": 0.5}',
    )
    weights: dict[str, float] | None = None
    if weights_json.strip() and weights_json.strip() != "{}":
        try:
            import json
            weights = json.loads(weights_json)
        except json.JSONDecodeError:
            st.error("权重 JSON 格式错误")

    col1, col2 = st.columns(2)
    with col1:
        start = st.text_input("开始日期", value="20230101")
    with col2:
        end = st.text_input("结束日期", value=default_end_date())

    initial_cash = st.number_input("总资金", value=DEFAULT_INITIAL_CASH, step=10000.0, format="%.2f")
    fee_rate = st.number_input("手续费率", value=DEFAULT_FEE_RATE, step=0.0001, format="%.6f")
    slippage = st.number_input("滑点", value=DEFAULT_SLIPPAGE, step=0.0001, format="%.6f")

    # 策略参数编辑
    st.markdown("---")
    st.subheader("🔧 策略参数")
    default_params = spec.default_parameters
    session_saved = st.session_state.get("saved_strategy_params", {})
    pref_params = session_saved.get("params", {}) if session_saved.get("strategy_key") == strategy_key else {}
    param_df = get_strategy_parameter_table(strategy_key)

    edited_params: dict[str, Any] = {}
    for name, default_value in default_params.items():
        value = pref_params.get(name, default_value)
        if isinstance(default_value, bool):
            edited_params[name] = st.toggle(name, value=bool(value), help=param_df[param_df["参数名"] == name]["中文解释"].values[0] if not param_df.empty else "")
        elif isinstance(default_value, int):
            edited_params[name] = st.number_input(name, value=int(value), step=1, format="%d", help=param_df[param_df["参数名"] == name]["中文解释"].values[0] if not param_df.empty else "")
        elif isinstance(default_value, float):
            edited_params[name] = st.number_input(name, value=float(value), step=0.1, format="%.4f", help=param_df[param_df["参数名"] == name]["中文解释"].values[0] if not param_df.empty else "")
        else:
            edited_params[name] = st.text_input(name, value=str(value), help=param_df[param_df["参数名"] == name]["中文解释"].values[0] if not param_df.empty else "")

    run_btn = st.button("🚀 运行组合回测", type="primary", use_container_width=True)


# ────────────────────────────── 主区域 ──────────────────────────────
if run_btn:
    if len(symbols) < 2:
        st.error("组合回测至少需要 2 个标的")
        st.stop()

    with st.spinner(f"正在对 {len(symbols)} 个标的运行组合回测..."):
        try:
            _, result, actual_symbols = run_portfolio_pipeline(
                symbols=symbols,
                start=start,
                end=end,
                initial_cash=initial_cash,
                fee_rate=fee_rate,
                slippage=slippage,
                strategy_name=strategy_key,
                weights=weights,
                strategy_params=edited_params,
            )
        except Exception as exc:
            st.error(f"组合回测失败：{exc}")
            st.stop()

    st.session_state["last_portfolio_result"] = result
    st.session_state["last_portfolio_symbols"] = actual_symbols
    st.session_state["last_portfolio_strategy"] = strategy_key
    st.session_state["last_portfolio_context"] = {
        "start_date": start,
        "end_date": end,
        "frequency": "daily",
        "initial_cash": float(initial_cash),
        "fee_rate": float(fee_rate),
        "slippage": float(slippage),
        "strategy_params": edited_params,
    }

    st.success(f"组合回测完成！标的数：{len(actual_symbols)}")

# 展示结果
if "last_portfolio_result" in st.session_state:
    result = st.session_state["last_portfolio_result"]
    actual_symbols = st.session_state["last_portfolio_symbols"]
    strategy_key = st.session_state["last_portfolio_strategy"]

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

    tab_chart, tab_stats, tab_trades, tab_daily, tab_per_symbol, tab_logs = st.tabs(
        ["📈 资金曲线", "📋 统计指标", "📝 成交记录", "📅 每日盈亏", "🔍 子账户汇总", "📜 运行日志"]
    )

    with tab_chart:
        if not result.equity_curve.empty:
            st.line_chart(result.equity_curve.set_index("date")["equity"], use_container_width=True)
        else:
            st.info("无资金曲线数据")

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

    with tab_per_symbol:
        if result.per_symbol_results:
            rows = []
            for sym, r in result.per_symbol_results.items():
                rows.append({
                    "标的": sym,
                    "总收益率": format_percent(r.total_return),
                    "最终资金": f"{r.final_cash:.2f}",
                    "最大回撤": format_percent(r.max_drawdown),
                    "交易次数": r.trade_count,
                    "胜率": format_percent(r.win_rate),
                    "Sharpe": f"{r.statistics.get('sharpe_ratio', 0):.2f}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("无子账户数据")

    with tab_logs:
        if result.logs:
            st.text_area("日志", value="\n".join(result.logs), height=400)
        else:
            st.info("无日志")
