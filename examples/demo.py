from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import run_pipeline
from src.utils import format_percent


def main() -> None:
    """运行一个 ETF 示例回测，适合新手快速验证项目是否可用。"""
    symbol = "510300"
    data, result, price_plot, equity_plot, _, _ = run_pipeline(
        symbol=symbol,
        start="20230101",
        end="20260508",
        initial_cash=100000,
        fee_rate=0.0003,
    )
    print(f"示例代码：{symbol}")
    print(f"数据行数：{len(data)}")
    print(f"最终资金：{result.final_cash:.2f}")
    print(f"总收益率：{format_percent(result.total_return)}")
    print(f"K线指标图：{price_plot}")
    print(f"资金曲线图：{equity_plot}")


if __name__ == "__main__":
    main()
