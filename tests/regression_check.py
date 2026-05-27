from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest import run_strategy_backtest
from src.data_fetcher import fetch_daily_data


def main() -> int:
    baseline_path = PROJECT_ROOT / "tests" / "baselines.json"
    config = json.loads(baseline_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for case in config.get("cases", []):
        name = case["name"]
        symbol = case["symbol"]
        frequency = case["frequency"]
        data = fetch_daily_data(
            symbol=symbol,
            start_date=case["start"],
            end_date=case["end"],
            frequency=frequency,
        )
        result = run_strategy_backtest(
            data=data.assign(symbol=symbol),
            strategy_name=case["strategy"],
            strategy_setting=case.get("params", {}),
        )
        baseline_return = case.get("baseline_total_return", result.total_return)
        baseline_dd = case.get("baseline_max_drawdown", result.max_drawdown)
        tol_ret = case.get("tolerance", {}).get("total_return_abs", 0.2)
        tol_dd = case.get("tolerance", {}).get("max_drawdown_abs", 0.2)

        if abs(result.total_return - baseline_return) > tol_ret:
            failures.append(
                f"{name}: total_return drift {result.total_return:.4f} vs {baseline_return:.4f} > {tol_ret:.4f}"
            )
        if abs(result.max_drawdown - baseline_dd) > tol_dd:
            failures.append(
                f"{name}: max_drawdown drift {result.max_drawdown:.4f} vs {baseline_dd:.4f} > {tol_dd:.4f}"
            )
        print(
            f"[OK] {name}: return={result.total_return:.4f}, max_dd={result.max_drawdown:.4f}, "
            f"sharpe={result.statistics.get('sharpe_ratio', 0):.2f}"
        )

    if failures:
        print("\n[FAILED]")
        for f in failures:
            print(f"- {f}")
        return 1
    print("\n[PASS] Regression check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
