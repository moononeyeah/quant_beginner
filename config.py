from datetime import datetime
from pathlib import Path


# 项目根目录，其他路径都基于它生成，避免运行位置变化导致找不到文件。
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

# 回测默认参数，新手可以先从这里修改。
DEFAULT_INITIAL_CASH = 100000.0
DEFAULT_FEE_RATE = 0.0003
DEFAULT_SLIPPAGE = 0.0

# 常用均线窗口。
MA_WINDOWS = (5, 10, 20, 60)

# ETF 轮动默认参数。
DEFAULT_ROTATION_SYMBOLS = ["510300", "159915", "512100", "518880", "513100"]
DEFAULT_ROTATION_LOOKBACK_DAYS = 20


def default_end_date() -> str:
    """返回今日日期，供默认日线回测结束日使用。"""
    return datetime.now().strftime("%Y%m%d")


def default_intraday_start() -> str:
    """返回今日开盘时间，供分钟线回测默认开始时间使用。"""
    return datetime.now().strftime("%Y-%m-%d 09:30:00")


def default_intraday_end() -> str:
    """返回当前时间，供分钟线回测默认结束时间使用。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
