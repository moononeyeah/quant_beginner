from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_TEST_SYMBOLS, default_end_date
from src.data_fetcher import fetch_daily_data


INDEX_SYMBOLS = {
    "000016", "000300", "000688", "000852", "000905", "000985",
    "399001", "399006",
}


def is_index_symbol(symbol: str) -> bool:
    return str(symbol).strip() in INDEX_SYMBOLS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量更新本地测试行情缓存")
    parser.add_argument("--symbols", default=",".join(DEFAULT_TEST_SYMBOLS), help="代码列表，逗号分隔")
    parser.add_argument("--daily-start", default="20200101", help="日线开始日期，YYYYMMDD")
    parser.add_argument("--daily-end", default=default_end_date(), help="日线结束日期，YYYYMMDD")
    parser.add_argument("--with-minute", action="store_true", help="额外拉取分钟线样本")
    parser.add_argument("--minute-period", default="5", choices=["1", "5", "15", "30", "60"], help="分钟线周期")
    parser.add_argument("--minute-days", type=int, default=5, help="分钟线回看天数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise ValueError("symbols 不能为空")

    print(f"开始更新测试数据，标的数：{len(symbols)}")
    for symbol in symbols:
        try:
            daily_df = fetch_daily_data(
                symbol=symbol,
                start_date=args.daily_start,
                end_date=args.daily_end,
                frequency="daily",
                use_cache=False,
            )
            print(f"[daily] {symbol}: {len(daily_df)} 行，最新={daily_df['date'].max()}")
        except Exception as exc:
            print(f"[daily] {symbol}: 失败，{exc}")

    if not args.with_minute:
        return

    end_dt = datetime.now().replace(second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=max(args.minute_days, 1))
    start_text = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_text = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    print(f"开始更新分钟线样本：{start_text} -> {end_text}")

    for symbol in symbols:
        if is_index_symbol(symbol):
            print(f"[{args.minute_period}m] {symbol}: 跳过（指数代码默认不拉取分钟线）")
            continue
        try:
            minute_df = fetch_daily_data(
                symbol=symbol,
                start_date=start_text,
                end_date=end_text,
                frequency=args.minute_period,
                use_cache=False,
            )
            print(
                f"[{args.minute_period}m] {symbol}: {len(minute_df)} 行，"
                f"最新={minute_df['date'].max()}"
            )
        except Exception as exc:
            print(f"[{args.minute_period}m] {symbol}: 失败，{exc}")


if __name__ == "__main__":
    main()
