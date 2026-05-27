from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "backtest_history.db"

st.set_page_config(page_title="实验中心", page_icon="🧭", layout="wide")
st.title("🧭 实验中心")

if not DB_PATH.exists():
    st.info("暂无实验数据")
    st.stop()

conn = sqlite3.connect(str(DB_PATH))
df = pd.read_sql_query("SELECT * FROM backtest_records ORDER BY created_at DESC", conn)
conn.close()

if df.empty:
    st.info("暂无历史记录")
    st.stop()

exp = st.text_input("按 experiment_id 过滤（留空显示全部）", value="")
run_types = sorted(x for x in df.get("run_type", pd.Series(dtype=str)).dropna().unique().tolist() if x)
selected_types = st.multiselect("运行类型", options=run_types, default=run_types)

view = df.copy()
if exp.strip():
    view = view[view.get("experiment_id", "").astype(str) == exp.strip()]
if selected_types:
    view = view[view.get("run_type", "").astype(str).isin(selected_types)]

st.dataframe(
    view[
        [
            c
            for c in [
                "id", "created_at", "experiment_id", "run_type", "name", "strategy_key",
                "symbols", "start_date", "end_date", "total_return", "max_drawdown", "sharpe_ratio"
            ]
            if c in view.columns
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

if not view.empty:
    st.subheader("实验聚合")
    grp = (
        view.groupby(["experiment_id", "run_type"], dropna=False)
        .agg(
            runs=("id", "count"),
            avg_return=("total_return", "mean"),
            avg_sharpe=("sharpe_ratio", "mean"),
            avg_max_dd=("max_drawdown", "mean"),
        )
        .reset_index()
        .sort_values("runs", ascending=False)
    )
    st.dataframe(grp, use_container_width=True, hide_index=True)
    if "avg_return" in grp.columns and "avg_sharpe" in grp.columns:
        st.bar_chart(grp.set_index("experiment_id")[["avg_return", "avg_sharpe"]], use_container_width=True)
