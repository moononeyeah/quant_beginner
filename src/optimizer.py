from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable

import pandas as pd

from src.backtest import run_strategy_backtest
from src.strategies import get_strategy_spec


@dataclass
class OptimizationResult:
    """参数优化结果。"""

    results_df: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    target: str = "total_return"
    total_combinations: int = 0
    completed: int = 0
    elapsed_seconds: float = 0.0

    @property
    def best_result(self) -> dict[str, Any] | None:
        if self.results_df.empty or self.target not in self.results_df.columns:
            return None
        idx = self.results_df[self.target].idxmax()
        return self.results_df.loc[idx].to_dict()


@dataclass
class OptimizationTask:
    """单个优化任务。"""

    data: pd.DataFrame = field(repr=False)
    strategy_name: str
    base_setting: dict[str, Any]
    param_values: tuple[Any, ...]
    param_keys: tuple[str, ...]
    initial_cash: float
    fee_rate: float
    slippage: float
    size: float
    pricetick: float


def _run_single_task(task: OptimizationTask) -> dict[str, Any]:
    """在子进程中运行单个回测任务。"""
    setting = dict(task.base_setting)
    setting.update(dict(zip(task.param_keys, task.param_values)))
    try:
        result = run_strategy_backtest(
            data=task.data,
            strategy_name=task.strategy_name,
            initial_cash=task.initial_cash,
            fee_rate=task.fee_rate,
            slippage=task.slippage,
            strategy_setting=setting,
            size=task.size,
            pricetick=task.pricetick,
        )
        row: dict[str, Any] = {"strategy": task.strategy_name}
        row.update(setting)
        row.update(result.statistics)
        return row
    except Exception as exc:
        row = {"strategy": task.strategy_name, "error": str(exc)}
        row.update(setting)
        return row


def optimize_strategy_parallel(
    data: pd.DataFrame,
    strategy_name: str,
    base_setting: dict[str, Any],
    optimization_grid: dict[str, list[Any]],
    initial_cash: float = 100000.0,
    fee_rate: float = 0.0003,
    slippage: float = 0.0,
    size: float = 1.0,
    pricetick: float = 0.01,
    target: str = "total_return",
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> OptimizationResult:
    """
    多进程并行参数优化。

    Args:
        data: 行情数据
        strategy_name: 策略名称
        base_setting: 基础参数设置
        optimization_grid: 参数网格，如 {"fast_window": [5, 10, 20], "slow_window": [20, 30, 60]}
        initial_cash: 初始资金
        fee_rate: 手续费率
        slippage: 滑点
        size: 合约乘数
        pricetick: 最小价格变动
        target: 排序目标指标
        max_workers: 最大并行进程数，默认 CPU 核心数
        progress_callback: 进度回调，接收 (completed, total)

    Returns:
        OptimizationResult
    """
    if not optimization_grid:
        raise ValueError("参数优化网格为空")

    spec = get_strategy_spec(strategy_name)
    valid_params = set(spec.default_parameters.keys())
    invalid_keys = [key for key in optimization_grid.keys() if key not in valid_params]
    if invalid_keys:
        raise ValueError(f"优化参数不属于当前策略：{invalid_keys}；可用参数为：{sorted(valid_params)}")

    keys = list(optimization_grid.keys())
    values_list = [optimization_grid[key] for key in keys]
    combinations = list(product(*values_list))
    total = len(combinations)
    if total == 0:
        raise ValueError("参数组合数为 0")
    if total > 5000:
        raise ValueError(f"参数组合数过多 ({total})，请缩小优化范围或精简参数网格")

    tasks = [
        OptimizationTask(
            data=data,
            strategy_name=strategy_name,
            base_setting=dict(base_setting),
            param_values=values,
            param_keys=tuple(keys),
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage=slippage,
            size=size,
            pricetick=pricetick,
        )
        for values in combinations
    ]

    workers = max_workers or max(1, mp.cpu_count() - 1)
    results: list[dict[str, Any]] = []
    completed = 0

    # 在 macOS 上使用 spawn 启动方式避免 fork 问题
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=min(workers, total)) as pool:
        for row in pool.imap_unordered(_run_single_task, tasks):
            results.append(row)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    df = pd.DataFrame(results)
    if target in df.columns:
        # 将包含 error 的行放到最后
        if "error" in df.columns:
            df = df.sort_values(
                by=[target],
                ascending=False,
                na_position="last",
            ).reset_index(drop=True)
        else:
            df = df.sort_values(target, ascending=False).reset_index(drop=True)

    return OptimizationResult(
        results_df=df,
        target=target,
        total_combinations=total,
        completed=completed,
        elapsed_seconds=0.0,
    )


def optimize_strategy(
    data: pd.DataFrame,
    strategy_name: str,
    base_setting: dict[str, Any],
    optimization_grid: dict[str, list[Any]],
    initial_cash: float,
    fee_rate: float,
    slippage: float,
    size: float = 1.0,
    pricetick: float = 0.01,
    target: str = "total_return",
    use_parallel: bool = True,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """
    兼容旧接口的参数优化入口。
    默认使用多进程，可传 use_parallel=False 回退到单进程。
    """
    if use_parallel:
        opt_result = optimize_strategy_parallel(
            data=data,
            strategy_name=strategy_name,
            base_setting=base_setting,
            optimization_grid=optimization_grid,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage=slippage,
            size=size,
            pricetick=pricetick,
            target=target,
            max_workers=max_workers,
            progress_callback=progress_callback,
        )
        return opt_result.results_df

    # 单进程回退（兼容旧代码）
    from src.backtest import optimize_strategy as _legacy_optimize

    return _legacy_optimize(
        data=data,
        strategy_name=strategy_name,
        base_setting=base_setting,
        optimization_grid=optimization_grid,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        target=target,
    )
