from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
import uuid

import pandas as pd
import streamlit as st
from main import run_pipeline, run_portfolio_pipeline

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
            notes TEXT,
            run_type TEXT DEFAULT 'normal',
            experiment_id TEXT DEFAULT ''
        )
    """)
    # 兼容旧表结构
    cols = pd.read_sql_query("PRAGMA table_info(backtest_records)", conn)["name"].tolist()
    if "run_type" not in cols:
        conn.execute("ALTER TABLE backtest_records ADD COLUMN run_type TEXT DEFAULT 'normal'")
    if "experiment_id" not in cols:
        conn.execute("ALTER TABLE backtest_records ADD COLUMN experiment_id TEXT DEFAULT ''")
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
    run_type: str = "normal",
    experiment_id: str = "",
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
         statistics_json, notes, run_type, experiment_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            run_type,
            experiment_id,
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


def _parse_strategy_params(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


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
    run_type = st.selectbox("运行类型", ["normal", "optimize", "walk_forward"], index=0)
    experiment_id = st.text_input("实验ID（可选）", value=uuid.uuid4().hex[:8])
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
                run_type=run_type,
                experiment_id=experiment_id.strip(),
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
                run_type=run_type,
                experiment_id=experiment_id.strip(),
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
        "run_type", "experiment_id",
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

    st.markdown("---")
    st.subheader("🔁 一键复跑")
    rerun_id = st.number_input("输入要复跑的记录 ID", value=0, step=1, min_value=0, key="rerun_id")
    if rerun_id > 0 and st.button("开始复跑", type="primary"):
        rec_df = df[df["id"] == int(rerun_id)]
        if rec_df.empty:
            st.error("未找到对应记录")
            st.stop()
        rec = rec_df.iloc[0]
        strategy_params = _parse_strategy_params(str(rec.get("strategy_params", "")))
        start_date = str(rec.get("start_date", ""))
        end_date = str(rec.get("end_date", ""))
        frequency = str(rec.get("frequency", "daily") or "daily")
        initial_cash = float(rec.get("initial_cash", 100000.0))
        fee_rate = float(rec.get("fee_rate", 0.0003))
        slippage = float(rec.get("slippage", 0.0))
        strategy_key = str(rec.get("strategy_key", "double_ma"))
        symbols = str(rec.get("symbols", "")).strip()
        backtest_type = str(rec.get("backtest_type", "single"))

        if not start_date or not end_date or not symbols:
            st.error("该历史记录缺少关键参数（symbols/start/end），无法复跑")
            st.stop()

        with st.spinner("正在复跑历史记录..."):
            try:
                if backtest_type == "portfolio":
                    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
                    _, result, actual_symbols = run_portfolio_pipeline(
                        symbols=symbol_list,
                        start=start_date,
                        end=end_date,
                        initial_cash=initial_cash,
                        fee_rate=fee_rate,
                        slippage=slippage,
                        strategy_name=strategy_key,
                        strategy_params=strategy_params,
                    )
                    st.session_state["last_portfolio_result"] = result
                    st.session_state["last_portfolio_symbols"] = actual_symbols
                    st.session_state["last_portfolio_strategy"] = strategy_key
                    st.session_state["last_portfolio_context"] = {
                        "start_date": start_date,
                        "end_date": end_date,
                        "frequency": frequency,
                        "initial_cash": initial_cash,
                        "fee_rate": fee_rate,
                        "slippage": slippage,
                        "strategy_params": strategy_params,
                    }
                else:
                    symbol = symbols.split(",")[0].strip()
                    _, result, _, _, _, symbol_label = run_pipeline(
                        symbol=symbol,
                        start=start_date,
                        end=end_date,
                        initial_cash=initial_cash,
                        fee_rate=fee_rate,
                        slippage=slippage,
                        frequency=frequency,
                        strategy_name=strategy_key,
                        strategy_params=strategy_params,
                    )
                    st.session_state["last_single_result"] = result
                    st.session_state["last_single_symbol"] = symbol_label
                    st.session_state["last_single_strategy"] = strategy_key
                    st.session_state["last_single_context"] = {
                        "start_date": start_date,
                        "end_date": end_date,
                        "frequency": frequency,
                        "initial_cash": initial_cash,
                        "fee_rate": fee_rate,
                        "slippage": slippage,
                        "strategy_params": strategy_params,
                    }
            except Exception as exc:
                st.error(f"复跑失败：{exc}")
                st.stop()
        st.success("复跑完成，结果已写入当前会话。可前往对应页面查看。")

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

    st.markdown("---")
    st.subheader("🧾 导出报告")
    export_ids = st.text_input("导出记录 ID（逗号分隔）", placeholder="例如: 2,3,5")
    if export_ids.strip() and st.button("导出 Markdown + CSV"):
        try:
            ids = [int(x.strip()) for x in export_ids.split(",") if x.strip()]
            export_df = df[df["id"].isin(ids)].copy()
            if export_df.empty:
                st.warning("未找到要导出的记录")
            else:
                report_dir = Path(__file__).resolve().parents[1] / "outputs" / "reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_path = report_dir / f"report_{ts}.csv"
                md_path = report_dir / f"report_{ts}.md"
                export_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                lines = ["# Backtest Report", "", f"- Export Time: {datetime.now().isoformat(timespec='seconds')}", ""]
                for _, row in export_df.iterrows():
                    lines.append(f"## {row.get('name', '')} (ID {row.get('id', '')})")
                    lines.append(f"- Strategy: `{row.get('strategy_key', '')}`")
                    lines.append(f"- Symbols: `{row.get('symbols', '')}`")
                    lines.append(f"- Period: `{row.get('start_date', '')}` ~ `{row.get('end_date', '')}` ({row.get('frequency', '')})")
                    lines.append(f"- Return: `{row.get('total_return', 0)}` | MaxDD: `{row.get('max_drawdown', 0)}` | Sharpe: `{row.get('sharpe_ratio', 0)}`")
                    lines.append("")
                md_path.write_text("\n".join(lines), encoding="utf-8")
                st.success(f"已导出：{md_path.name}, {csv_path.name}")
        except ValueError:
            st.error("ID 格式错误")
