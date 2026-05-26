from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "backtest_history.db"


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            name TEXT NOT NULL,
            backtest_type TEXT NOT NULL,
            strategy_key TEXT NOT NULL,
            symbols TEXT,
            start_date TEXT,
            end_date TEXT,
            frequency TEXT,
            initial_cash REAL,
            fee_rate REAL,
            slippage REAL,
            strategy_params TEXT,
            total_return REAL,
            max_drawdown REAL,
            sharpe_ratio REAL,
            sortino_ratio REAL,
            calmar_ratio REAL,
            annual_return REAL,
            win_rate REAL,
            profit_loss_ratio REAL,
            trade_count INTEGER,
            total_days INTEGER,
            statistics_json TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_record(
    name: str,
    backtest_type: str,
    strategy_key: str,
    symbols: str,
    start_date: str,
    end_date: str,
    frequency: str,
    initial_cash: float,
    fee_rate: float,
    slippage: float,
    strategy_params: dict[str, Any],
    statistics: dict[str, Any],
    notes: str = "",
) -> None:
    _init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        INSERT INTO backtest_records
        (created_at, name, backtest_type, strategy_key, symbols, start_date, end_date,
         frequency, initial_cash, fee_rate, slippage, strategy_params,
         total_return, max_drawdown, sharpe_ratio, sortino_ratio, calmar_ratio,
         annual_return, win_rate, profit_loss_ratio, trade_count, total_days,
         statistics_json, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(),
            name,
            backtest_type,
            strategy_key,
            symbols,
            start_date,
            end_date,
            frequency,
            initial_cash,
            fee_rate,
            slippage,
            json.dumps(strategy_params, ensure_ascii=False),
            statistics.get("total_return", 0.0),
            statistics.get("max_ddpercent", statistics.get("max_drawdown", 0.0)),
            statistics.get("sharpe_ratio", 0.0),
            statistics.get("sortino_ratio", 0.0),
            statistics.get("calmar_ratio", 0.0),
            statistics.get("annual_return", 0.0),
            statistics.get("win_rate", 0.0),
            statistics.get("profit_loss_ratio", 0.0),
            statistics.get("total_trade_count", 0),
            statistics.get("total_days", 0),
            json.dumps(statistics, ensure_ascii=False),
            notes,
        ),
    )
    conn.commit()
    conn.close()


def load_records() -> pd.DataFrame:
    _init_db()
    conn = sqlite3.connect(str(DB_PATH))
    df = pd.read_sql_query("SELECT * FROM backtest_records ORDER BY created_at DESC", conn)
    conn.close()
    return df


def delete_record(record_id: int) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM backtest_records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


st.set_page_config(page_title="历史记录", page_icon="📚", layout="wide")

st.title("📚 历史记录")

# ────────────────────────────── 保存当前回测 ──────────────────────────────
st.subheader("💾 保存当前回测")

save_type = st.selectbox("回测类型", ["单标回测", "组合回测"], key="save_type")

if save_type == "单标回测" and "last_single_result" in st.session_state:
    result = st.session_state["last_single_result"]
    default_name = f"{st.session_state['last_single_strategy']}_{st.session_state['last_single_symbol']}"
elif save_type == "组合回测" and "last_portfolio_result" in st.session_state:
    result = st.session_state["last_portfolio_result"]
    default_name = f"{st.session_state['last_portfolio_strategy']}_portfolio"
else:
    result = None
    default_name = ""

if result:
    save_name = st.text_input("记录名称", value=default_name, key="save_name")
    save_notes = st.text_area("备注", value="", key="save_notes")
    if st.button("💾 保存到历史记录", type="primary"):
        if save_type == "单标回测":
            ctx = st.session_state.get("last_single_context", {})
            save_record(
                name=save_name,
                backtest_type="single",
                strategy_key=st.session_state["last_single_strategy"],
                symbols=st.session_state["last_single_symbol"],
                start_date=str(ctx.get("start_date", "")),
                end_date=str(ctx.get("end_date", "")),
                frequency=str(ctx.get("frequency", "")),
                initial_cash=float(ctx.get("initial_cash", result.initial_cash)),
                fee_rate=float(ctx.get("fee_rate", 0.0003)),
                slippage=float(ctx.get("slippage", 0.0)),
                strategy_params=dict(ctx.get("strategy_params", {})),
                statistics=result.statistics,
                notes=save_notes,
            )
        else:
            ctx = st.session_state.get("last_portfolio_context", {})
            save_record(
                name=save_name,
                backtest_type="portfolio",
                strategy_key=st.session_state["last_portfolio_strategy"],
                symbols=",".join(st.session_state["last_portfolio_symbols"]),
                start_date=str(ctx.get("start_date", "")),
                end_date=str(ctx.get("end_date", "")),
                frequency=str(ctx.get("frequency", "")),
                initial_cash=float(ctx.get("initial_cash", result.initial_cash)),
                fee_rate=float(ctx.get("fee_rate", 0.0003)),
                slippage=float(ctx.get("slippage", 0.0)),
                strategy_params=dict(ctx.get("strategy_params", {})),
                statistics=result.statistics,
                notes=save_notes,
            )
        st.success("保存成功！")
        st.rerun()
else:
    st.info(f"暂无{save_type}结果可保存。请先运行回测。")

st.markdown("---")

# ────────────────────────────── 历史记录列表 ──────────────────────────────
st.subheader("📋 历史记录列表")

df = load_records()
if df.empty:
    st.info("暂无历史记录")
else:
    # 展示关键列
    display_cols = [
        "id", "created_at", "name", "backtest_type", "strategy_key", "symbols",
        "start_date", "end_date", "frequency",
        "total_return", "max_drawdown", "sharpe_ratio", "sortino_ratio",
        "calmar_ratio", "annual_return", "win_rate", "trade_count", "notes",
    ]
    display_df = df[[c for c in display_cols if c in df.columns]].copy()
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # 删除功能
    st.markdown("---")
    st.subheader("🗑️ 删除记录")
    delete_id = st.number_input("输入要删除的记录 ID", value=0, step=1, min_value=0)
    if delete_id > 0 and st.button("确认删除"):
        delete_record(delete_id)
        st.success(f"已删除记录 #{delete_id}")
        st.rerun()

    # 对比功能
    st.markdown("---")
    st.subheader("📊 多组对比")
    compare_ids_str = st.text_input("输入要对比的记录 ID（逗号分隔）", placeholder="例如: 1,2,3")
    if compare_ids_str.strip():
        try:
            compare_ids = [int(x.strip()) for x in compare_ids_str.split(",")]
            compare_df = df[df["id"].isin(compare_ids)]
            if not compare_df.empty:
                chart_cols = ["total_return", "sharpe_ratio", "max_drawdown", "calmar_ratio"]
                chart_df = compare_df[["name"] + [c for c in chart_cols if c in compare_df.columns]].set_index("name")
                st.bar_chart(chart_df)
            else:
                st.warning("未找到指定记录")
        except ValueError:
            st.error("ID 格式错误")
