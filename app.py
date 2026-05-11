from __future__ import annotations

import json
import math
from typing import Any

import gradio as gr
import pandas as pd

from config import (
    DEFAULT_FEE_RATE,
    DEFAULT_INITIAL_CASH,
    DEFAULT_ROTATION_SYMBOLS,
    DEFAULT_SLIPPAGE,
    default_end_date,
    default_intraday_end,
    default_intraday_start,
)
from main import run_optimization_pipeline, run_pipeline
from src.plotter import plot_performance_dashboard
from src.strategies import (
    PARAMETER_DESCRIPTIONS,
    STRATEGY_SPECS,
    get_strategy_parameter_table,
    get_strategy_source,
    get_strategy_spec,
    list_strategy_catalog,
)
from src.utils import format_percent, friendly_error


DISPLAY_TO_KEY = {spec.display_name: key for key, spec in STRATEGY_SPECS.items()}
PARAMETER_TABLE_COLUMNS = ["参数名", "当前值", "类型", "中文解释"]

APP_CSS = ""


def _pretty_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _suggest_optimization_grid(strategy_key: str) -> str:
    spec = get_strategy_spec(strategy_key)
    grid: dict[str, list[Any]] = {}
    for name, value in spec.default_parameters.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            if value <= 3:
                grid[name] = [value, value + 1, value + 2]
            else:
                low = max(1, value // 2)
                grid[name] = sorted({low, value, max(low + 1, value * 2)})
        elif isinstance(value, float):
            low = round(max(0.0, value * 0.5), 4)
            mid = round(value, 4)
            high = round(value * 1.5 if value else 0.5, 4)
            grid[name] = [low, mid, high]

    if strategy_key == "rotation":
        grid = {"lookback_days": [10, 20, 30]}
    elif strategy_key == "double_ma":
        grid = {"fast_window": [5, 10, 20], "slow_window": [20, 30, 60]}

    return _pretty_json(grid)


def _default_dates_for_frequency(frequency: str) -> tuple[str, str]:
    if frequency == "daily":
        return "20230101", default_end_date()
    return default_intraday_start(), default_intraday_end()


def _date_help_text(frequency: str) -> str:
    if frequency == "daily":
        return "日线格式：YYYYMMDD。"
    return f"{frequency} 分钟线格式：YYYY-MM-DD HH:MM:SS。分钟线通常只支持较近时间段。"


def _strategy_meta_markdown(strategy_key: str) -> str:
    spec = get_strategy_spec(strategy_key)
    return "\n".join(
        [
            f"### {spec.display_name}",
            f"- 策略键：`{spec.key}`",
            f"- 分类：{spec.category}",
            f"- 引擎：{spec.engine_type}",
            f"- 支持周期：{spec.supports_frequency}",
            f"- 描述：{spec.description}",
        ]
    )


def _summary_markdown(result, strategy_key: str, frequency: str, symbol_label: str) -> str:
    spec = get_strategy_spec(strategy_key)
    lines = [
        "### 回测总览",
        f"- 策略：{spec.display_name}",
        f"- 标的：{symbol_label}",
        f"- 周期：{frequency}",
        f"- 初始资金：{result.initial_cash:,.2f}",
        f"- 最终资金：{result.final_cash:,.2f}",
        f"- 总收益率：{format_percent(result.total_return)}",
        f"- 年化收益：{format_percent(result.statistics.get('annual_return', 0.0))}",
        f"- 最大回撤：{format_percent(result.max_drawdown)}",
        f"- Sharpe：{result.statistics.get('sharpe_ratio', 0.0):.2f}",
        f"- 总交易日：{result.statistics.get('total_days', 0)}",
        f"- 交易次数：{result.trade_count}",
        f"- 胜率：{format_percent(result.win_rate)}",
    ]
    return "\n".join(lines)


def _statistics_table(statistics: dict[str, Any]) -> pd.DataFrame:
    if not statistics:
        return pd.DataFrame(columns=["指标", "数值"])
    rows = [(key, value) for key, value in statistics.items()]
    return pd.DataFrame(rows, columns=["指标", "数值"])


def _clean_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    for column in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[column]):
            result[column] = pd.to_datetime(result[column]).dt.strftime("%Y-%m-%d %H:%M:%S")
        elif result[column].dtype == object:
            continue
        elif pd.api.types.is_float_dtype(result[column]):
            result[column] = result[column].map(
                lambda value: round(float(value), 6) if pd.notna(value) and math.isfinite(float(value)) else value
            )
    return result


def _parse_json_dict(raw: str, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} 不是合法 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} 必须是 JSON 对象")
    return value


def _format_parameter_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _coerce_parameter_value(raw: Any, default_value: Any, name: str) -> Any:
    text = "" if raw is None else str(raw).strip()
    if text == "":
        raise ValueError(f"参数 {name} 不能为空")

    if isinstance(default_value, bool):
        lowered = text.lower()
        if lowered in {"true", "1", "yes", "y", "是", "开"}:
            return True
        if lowered in {"false", "0", "no", "n", "否", "关"}:
            return False
        raise ValueError(f"参数 {name} 必须是布尔值：true/false")
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        try:
            return int(float(text))
        except ValueError as exc:
            raise ValueError(f"参数 {name} 必须是整数") from exc
    if isinstance(default_value, float):
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(f"参数 {name} 必须是数字") from exc
    return text


def _strategy_parameter_editor_table(strategy_key: str, strategy_params_json: str) -> pd.DataFrame:
    spec = get_strategy_spec(strategy_key)
    defaults = spec.default_parameters
    current = defaults.copy()
    current.update(_parse_json_dict(strategy_params_json, "策略参数"))
    rows = [
        {
            "参数名": name,
            "当前值": _format_parameter_value(current.get(name, default_value)),
            "类型": type(default_value).__name__,
            "中文解释": PARAMETER_DESCRIPTIONS.get(name, "策略参数。可结合策略源码理解具体用途。"),
        }
        for name, default_value in defaults.items()
    ]
    return pd.DataFrame(rows, columns=PARAMETER_TABLE_COLUMNS)


def _strategy_parameter_help_markdown(strategy_key: str, strategy_params_json: str) -> str:
    spec = get_strategy_spec(strategy_key)
    defaults = spec.default_parameters
    try:
        current = defaults.copy()
        current.update(_parse_json_dict(strategy_params_json, "策略参数"))
    except ValueError:
        current = defaults

    if not defaults:
        return "当前策略没有额外策略参数。"

    lines = ["#### 策略参数中文解释"]
    for name, default_value in defaults.items():
        value = _format_parameter_value(current.get(name, default_value))
        description = PARAMETER_DESCRIPTIONS.get(name, "策略参数。可结合策略源码理解具体用途。")
        lines.append(f"- `{name}`：当前值 `{value}`，类型 `{type(default_value).__name__}`。{description}")
    return "\n".join(lines)


def _parameter_table_to_dict(strategy_key: str, table: Any) -> dict[str, Any]:
    spec = get_strategy_spec(strategy_key)
    defaults = spec.default_parameters
    if not defaults:
        return {}

    if isinstance(table, pd.DataFrame):
        df = table.copy()
    else:
        df = pd.DataFrame(table or [], columns=PARAMETER_TABLE_COLUMNS)

    if "参数名" not in df.columns or "当前值" not in df.columns:
        raise ValueError("策略参数表缺少“参数名”或“当前值”列")

    params: dict[str, Any] = {}
    for _, row in df.iterrows():
        name = str(row.get("参数名", "")).strip()
        if not name:
            continue
        if name not in defaults:
            raise ValueError(f"未知策略参数：{name}")
        params[name] = _coerce_parameter_value(row.get("当前值"), defaults[name], name)
    for name, default_value in defaults.items():
        params.setdefault(name, default_value)
    return params


def update_frequency_inputs(frequency: str):
    start_value, end_value = _default_dates_for_frequency(frequency)
    placeholder = "YYYYMMDD" if frequency == "daily" else "YYYY-MM-DD HH:MM:SS"
    return (
        gr.update(value=start_value, placeholder=placeholder),
        gr.update(value=end_value, placeholder=placeholder),
        gr.update(value=_date_help_text(frequency)),
    )


def update_strategy_inputs(strategy_label: str, frequency: str):
    strategy_key = DISPLAY_TO_KEY[strategy_label]
    spec = get_strategy_spec(strategy_key)
    params_json = _pretty_json(spec.default_parameters)
    optimization_grid_json = _suggest_optimization_grid(strategy_key)
    source_file, source_code = get_strategy_source(strategy_key)
    start_value, end_value = _default_dates_for_frequency("daily" if spec.engine_type == "portfolio" else frequency)
    placeholder = "YYYYMMDD" if (spec.engine_type == "portfolio" or frequency == "daily") else "YYYY-MM-DD HH:MM:SS"
    return (
        gr.update(value="daily" if spec.engine_type == "portfolio" else frequency, interactive=spec.engine_type != "portfolio"),
        gr.update(visible=spec.engine_type != "portfolio"),
        gr.update(visible=spec.engine_type == "portfolio"),
        gr.update(value=start_value, placeholder=placeholder),
        gr.update(value=end_value, placeholder=placeholder),
        gr.update(value=params_json),
        gr.update(value=optimization_grid_json),
        gr.update(value=_date_help_text("daily" if spec.engine_type == "portfolio" else frequency)),
        gr.update(value=_strategy_meta_markdown(strategy_key)),
        gr.update(value=get_strategy_parameter_table(strategy_key)),
        gr.update(value=source_file),
        gr.update(value=source_code),
        gr.update(value=_strategy_parameter_editor_table(strategy_key, params_json)),
    )


def open_parameter_modal(
    strategy_label: str,
    strategy_params_json: str,
):
    strategy_key = DISPLAY_TO_KEY[strategy_label]
    return (
        gr.update(visible=True),
        _strategy_parameter_editor_table(strategy_key, strategy_params_json),
    )


def close_parameter_modal():
    return gr.update(visible=False)


def run_gradio_backtest(
    strategy_label: str,
    symbol: str,
    rotation_symbols: str,
    frequency: str,
    start: str,
    end: str,
    initial_cash: float,
    fee_rate: float,
    slippage: float,
    strategy_params_json: str,
):
    try:
        strategy_key = DISPLAY_TO_KEY[strategy_label]
        strategy_params = _parse_json_dict(strategy_params_json, "策略参数")
        _, result, price_plot, equity_plot, debug_df, symbol_label = run_pipeline(
            symbol=symbol,
            start=start,
            end=end,
            initial_cash=float(initial_cash),
            fee_rate=float(fee_rate),
            slippage=float(slippage),
            frequency=frequency,
            strategy_name=strategy_key,
            rotation_symbols=rotation_symbols,
            strategy_params=strategy_params,
        )

        summary = _summary_markdown(result, strategy_key, frequency, symbol_label)
        stats_df = _statistics_table(result.statistics)
        trades_df = _clean_table(result.trades)
        daily_df = _clean_table(result.daily_results)
        debug_df = _clean_table(debug_df)
        logs_df = pd.DataFrame({"日志": result.logs}) if result.logs else pd.DataFrame(columns=["日志"])
        dashboard_plot = plot_performance_dashboard(result.daily_results)
        return summary, dashboard_plot, str(price_plot), str(equity_plot), stats_df, trades_df, daily_df, debug_df, logs_df
    except Exception as exc:
        empty = pd.DataFrame()
        logs_df = pd.DataFrame({"日志": [friendly_error("回测失败", exc)]})
        message = friendly_error("回测失败，请检查代码、时间格式、依赖安装和网络连接。", exc)
        return message, None, None, None, empty, empty, empty, empty, logs_df


def run_gradio_backtest_from_modal(
    strategy_label: str,
    symbol: str,
    rotation_symbols: str,
    frequency: str,
    start: str,
    end: str,
    initial_cash: float,
    fee_rate: float,
    slippage: float,
    strategy_params_table: Any,
):
    strategy_key = DISPLAY_TO_KEY[strategy_label]
    try:
        strategy_params = _parameter_table_to_dict(strategy_key, strategy_params_table)
    except Exception as exc:
        empty = pd.DataFrame()
        logs_df = pd.DataFrame({"日志": [friendly_error("参数解析失败", exc)]})
        message = friendly_error("参数解析失败，请检查弹窗里的参数值。", exc)
        return gr.update(visible=True), message, None, None, None, empty, empty, empty, empty, logs_df, _pretty_json({})

    summary, dashboard_plot, price_plot, equity_plot, stats_df, trades_df, daily_df, debug_df, logs_df = run_gradio_backtest(
        strategy_label=strategy_label,
        symbol=symbol,
        rotation_symbols=rotation_symbols,
        frequency=frequency,
        start=start,
        end=end,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage=slippage,
        strategy_params_json=_pretty_json(strategy_params),
    )
    return (
        gr.update(visible=False),
        summary,
        dashboard_plot,
        price_plot,
        equity_plot,
        stats_df,
        trades_df,
        daily_df,
        debug_df,
        logs_df,
        _pretty_json(strategy_params),
    )


def run_gradio_optimization(
    strategy_label: str,
    symbol: str,
    rotation_symbols: str,
    frequency: str,
    start: str,
    end: str,
    initial_cash: float,
    fee_rate: float,
    slippage: float,
    strategy_params_json: str,
    optimization_grid_json: str,
):
    try:
        strategy_key = DISPLAY_TO_KEY[strategy_label]
        strategy_params = _parse_json_dict(strategy_params_json, "策略参数")
        optimization_grid = _parse_json_dict(optimization_grid_json, "优化参数")
        if not optimization_grid:
            return pd.DataFrame({"错误": ["优化参数网格为空，请至少提供一个参数列表"]})
        result_df = run_optimization_pipeline(
            symbol=symbol,
            start=start,
            end=end,
            initial_cash=float(initial_cash),
            fee_rate=float(fee_rate),
            slippage=float(slippage),
            frequency=frequency,
            strategy_name=strategy_key,
            rotation_symbols=rotation_symbols,
            strategy_params=strategy_params,
            optimization_grid=optimization_grid,
        )
        return _clean_table(result_df)
    except Exception as exc:
        return pd.DataFrame({"错误": [friendly_error("参数优化失败", exc)]})


def build_app() -> gr.Blocks:
    default_strategy_key = "double_ma"
    default_strategy = get_strategy_spec(default_strategy_key)
    default_source_file, default_source_code = get_strategy_source(default_strategy_key)

    with gr.Blocks(title="Quant Backtester") as demo:
        if APP_CSS:
            gr.HTML(f"<style>{APP_CSS}</style>")
        gr.Markdown(
            "# Quant Backtester\n\n"
            "按 vn.py 的 CTA 回测方式重建：策略注册、数据获取、回测、参数优化、策略管理都在一个工作台里。"
        )

        with gr.Row():
            with gr.Column(scale=4, min_width=360):
                strategy_label = gr.Dropdown(
                    label="交易策略",
                    choices=[spec.display_name for spec in STRATEGY_SPECS.values()],
                    value=default_strategy.display_name,
                )
                symbol = gr.Textbox(label="交易代码", value="510300", placeholder="例如 510300 或 000001")
                rotation_symbols = gr.Textbox(
                    label="ETF 池",
                    value=",".join(DEFAULT_ROTATION_SYMBOLS),
                    placeholder="多个代码用逗号分隔",
                    visible=False,
                )
                frequency = gr.Dropdown(label="K线周期", choices=["daily", "1", "5", "15", "30", "60"], value="daily")
                start = gr.Textbox(label="开始时间", value="20230101", placeholder="YYYYMMDD")
                end = gr.Textbox(label="结束时间", value=default_end_date(), placeholder="YYYYMMDD")
                date_help = gr.Markdown(_date_help_text("daily"))

                with gr.Group():
                    initial_cash = gr.Number(label="回测资金", value=DEFAULT_INITIAL_CASH, precision=2)
                    fee_rate = gr.Number(label="手续费率", value=DEFAULT_FEE_RATE, precision=6)
                    slippage = gr.Number(label="滑点", value=DEFAULT_SLIPPAGE, precision=6)

                strategy_params_json = gr.Code(
                    label="策略参数 JSON",
                    value=_pretty_json(default_strategy.default_parameters),
                    language="json",
                    lines=14,
                )
                optimization_grid_json = gr.Code(
                    label="优化参数网格 JSON",
                    value=_suggest_optimization_grid(default_strategy_key),
                    language="json",
                    lines=10,
                )

                with gr.Row():
                    run_btn = gr.Button("开始回测", variant="primary")
                    optimize_btn = gr.Button("参数优化")

                gr.Markdown("点击“开始回测”后会先弹出参数确认窗口，可直接修改参数并查看中文解释。")

            with gr.Column(scale=8):
                summary = gr.Markdown("### 回测总览\n- 尚未运行")
                dashboard_plot = gr.Plot(label="业绩图表")

                with gr.Tabs():
                    with gr.Tab("图表"):
                        with gr.Row():
                            price_image = gr.Image(label="价格与信号", type="filepath")
                            equity_image = gr.Image(label="资金曲线", type="filepath")
                    with gr.Tab("统计指标"):
                        statistics_table = gr.Dataframe(label="统计指标", interactive=False, wrap=True)
                    with gr.Tab("成交记录"):
                        trades_table = gr.Dataframe(label="成交记录", interactive=False, wrap=True)
                    with gr.Tab("每日盈亏"):
                        daily_table = gr.Dataframe(label="每日盈亏", interactive=False, wrap=True)
                    with gr.Tab("策略输出"):
                        debug_table = gr.Dataframe(label="策略输出", interactive=False, wrap=True)
                    with gr.Tab("运行日志"):
                        logs_table = gr.Dataframe(label="日志", interactive=False, wrap=True)
                    with gr.Tab("参数优化"):
                        optimization_table = gr.Dataframe(label="优化结果", interactive=False, wrap=True)
                    with gr.Tab("策略管理"):
                        strategy_catalog = gr.Dataframe(label="策略目录", value=list_strategy_catalog(), interactive=False, wrap=True)
                        strategy_meta = gr.Markdown(_strategy_meta_markdown(default_strategy_key))
                        strategy_param_table = gr.Dataframe(
                            label="所选策略参数定义",
                            value=get_strategy_parameter_table(default_strategy_key),
                            interactive=False,
                            wrap=True,
                        )
                        strategy_source_file = gr.Textbox(label="源码文件", value=default_source_file, interactive=False)
                        strategy_source_code = gr.Code(label="策略源码预览", value=default_source_code, language="python", interactive=False)

        with gr.Group(visible=False) as parameter_modal:
            gr.Markdown("### 策略参数确认\n这里只修改策略参数。交易代码、周期、时间、资金等继续使用主界面的值。")
            modal_strategy_params_table = gr.Dataframe(
                label="策略参数表单（编辑“当前值”列）",
                value=_strategy_parameter_editor_table(default_strategy_key, _pretty_json(default_strategy.default_parameters)),
                headers=PARAMETER_TABLE_COLUMNS,
                datatype=["str", "str", "str", "str"],
                row_count=(1, "dynamic"),
                column_count=(4, "fixed"),
                interactive=True,
                wrap=True,
                max_height=320,
                show_row_numbers=True,
            )
            gr.Markdown(
                "说明：`参数名`、`类型`、`中文解释`为参考信息，请只改 `当前值`。布尔值用 `true/false`。"
            )
            with gr.Row():
                confirm_run_btn = gr.Button("确认并开始回测", variant="primary")
                cancel_run_btn = gr.Button("取消")

        frequency.change(
            fn=update_frequency_inputs,
            inputs=[frequency],
            outputs=[start, end, date_help],
        )
        strategy_label.change(
            fn=update_strategy_inputs,
            inputs=[strategy_label, frequency],
            outputs=[
                frequency,
                symbol,
                rotation_symbols,
                start,
                end,
                strategy_params_json,
                optimization_grid_json,
                date_help,
                strategy_meta,
                strategy_param_table,
                strategy_source_file,
                strategy_source_code,
                modal_strategy_params_table,
            ],
        )
        run_btn.click(
            fn=open_parameter_modal,
            inputs=[
                strategy_label,
                strategy_params_json,
            ],
            outputs=[
                parameter_modal,
                modal_strategy_params_table,
            ],
            queue=False,
        )
        cancel_run_btn.click(
            fn=close_parameter_modal,
            inputs=None,
            outputs=[parameter_modal],
            queue=False,
        )
        confirm_run_btn.click(
            fn=run_gradio_backtest_from_modal,
            inputs=[
                strategy_label,
                symbol,
                rotation_symbols,
                frequency,
                start,
                end,
                initial_cash,
                fee_rate,
                slippage,
                modal_strategy_params_table,
            ],
            outputs=[
                parameter_modal,
                summary,
                dashboard_plot,
                price_image,
                equity_image,
                statistics_table,
                trades_table,
                daily_table,
                debug_table,
                logs_table,
                strategy_params_json,
            ],
        )
        optimize_btn.click(
            fn=run_gradio_optimization,
            inputs=[
                strategy_label,
                symbol,
                rotation_symbols,
                frequency,
                start,
                end,
                initial_cash,
                fee_rate,
                slippage,
                strategy_params_json,
                optimization_grid_json,
            ],
            outputs=[optimization_table],
        )

    return demo


if __name__ == "__main__":
    build_app().launch(theme=gr.themes.Soft())
