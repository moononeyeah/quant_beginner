from __future__ import annotations

import sys
from pathlib import Path
import re

import pandas as pd

from config import DATA_DIR
from src.utils import ensure_dir, normalize_date, normalize_datetime


STANDARD_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
SUPPORTED_FREQUENCIES = {"daily", "1", "5", "15", "30", "60"}


def _cache_key_part(value: str) -> str:
    """把日期或日期时间转换成适合文件名的片段。"""
    return str(value).strip().replace(" ", "_").replace(":", "-")


def _cache_path(symbol: str, start_date: str, end_date: str, frequency: str, cache_dir: Path) -> Path:
    """根据代码、频率和日期生成缓存文件路径，避免不同区间缓存互相覆盖。"""
    safe_symbol = str(symbol).strip()
    return cache_dir / f"{safe_symbol}_{frequency}_{_cache_key_part(start_date)}_{_cache_key_part(end_date)}.csv"


def _read_cache_file(cache_file: Path) -> pd.DataFrame:
    df = pd.read_csv(cache_file)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _filter_cached_range(df: pd.DataFrame, start: str, end: str, frequency: str) -> pd.DataFrame:
    result = df.copy()
    start_ts = pd.to_datetime(start)
    end_ts = pd.to_datetime(end)
    result = result[(result["date"] >= start_ts) & (result["date"] <= end_ts)].copy()
    if result.empty:
        return result
    return result.sort_values("date").reset_index(drop=True)


def _find_best_compatible_cache(
    symbol: str,
    start: str,
    end: str,
    frequency: str,
    cache_dir: Path,
) -> pd.DataFrame | None:
    """
    在没有精确缓存时，尝试复用本地已有的更大时间范围缓存。
    例如请求到 20260509，但本地已有到 20260508 的日线缓存，则直接回退使用。
    """
    safe_symbol = str(symbol).strip()
    patterns: list[re.Pattern[str]] = [
        re.compile(
            rf"^{re.escape(safe_symbol)}_{re.escape(frequency)}_(.+)_(.+)\.csv$"
        ),
    ]
    if frequency == "daily":
        patterns.append(re.compile(rf"^{re.escape(safe_symbol)}_(\d{{8}})_(\d{{8}})\.csv$"))

    candidates: list[tuple[pd.Timestamp, pd.Timestamp, Path]] = []
    for path in cache_dir.glob("*.csv"):
        for pattern in patterns:
            match = pattern.match(path.name)
            if not match:
                continue
            try:
                file_start = pd.to_datetime(match.group(1).replace("_", " "))
                file_end = pd.to_datetime(match.group(2).replace("_", " "))
            except Exception:
                continue
            candidates.append((file_start, file_end, path))
            break

    if not candidates:
        return None

    request_start = pd.to_datetime(start)
    request_end = pd.to_datetime(end)

    exact_or_covering: list[tuple[pd.Timestamp, pd.Timestamp, Path]] = []
    partial_overlap: list[tuple[pd.Timestamp, pd.Timestamp, Path]] = []
    for file_start, file_end, path in candidates:
        if file_start <= request_start and file_end >= request_end:
            exact_or_covering.append((file_start, file_end, path))
        elif file_end >= request_start and file_start <= request_end:
            partial_overlap.append((file_start, file_end, path))

    ranked = sorted(
        exact_or_covering or partial_overlap,
        key=lambda item: (
            min(abs((item[0] - request_start).days), 999999),
            abs((item[1] - request_end).days),
            -((item[1] - item[0]).days),
        ),
    )

    for _, _, path in ranked:
        try:
            cached = _read_cache_file(path)
            filtered = _filter_cached_range(cached, start, end, frequency)
            if not filtered.empty:
                return filtered
            if frequency == "daily":
                # 周末/节假日请求常见：允许返回到请求结束日前最近一个交易日的数据。
                fallback = cached[cached["date"] >= request_start].copy()
                if not fallback.empty and fallback["date"].max() <= request_end:
                    return fallback.sort_values("date").reset_index(drop=True)
        except Exception:
            continue
    return None


def _rename_columns(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """兼容 akshare 中文字段和英文字段，统一成项目标准字段。"""
    column_map = {
        "时间": "date",
        "日期": "date",
        "day": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "date": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }
    renamed = df.rename(columns={col: column_map.get(col, col) for col in df.columns})
    missing = [col for col in STANDARD_COLUMNS if col not in renamed.columns]
    if missing:
        raise ValueError(f"{mode}数据缺少必要字段：{missing}，请检查 akshare 接口返回格式")
    return renamed[STANDARD_COLUMNS].copy()


def _require_supported_python() -> None:
    """校验 Python 版本，避免在过低版本上运行。"""
    if sys.version_info < (3, 10):
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise RuntimeError(f"当前 Python 版本为 {current}，请使用 Python 3.10 或更高版本")


def _import_akshare():
    """导入 akshare，并在缺失时返回明确安装提示。"""
    try:
        import akshare as ak
    except Exception as exc:
        raise ImportError(
            "未安装 akshare，请在项目根目录运行 `pip install -r requirements.txt`，"
            "或进入 `quant_beginner` 目录后运行 `pip install -r requirements.txt`"
        ) from exc
    return ak


def _fetch_daily(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """优先按 ETF 获取日线，失败后按 A 股股票获取。"""
    _require_supported_python()
    ak = _import_akshare()

    errors: list[str] = []
    try:
        return ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
    except Exception as exc:
        errors.append(f"ETF 日线接口失败：{exc}")

    try:
        return ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
    except Exception as exc:
        errors.append(f"A股日线接口失败：{exc}")

    raise RuntimeError("无法获取日线行情；" + "；".join(errors))


def _fetch_minute(symbol: str, start_date: str, end_date: str, period: str) -> pd.DataFrame:
    """优先按 ETF 获取分钟线，失败后按 A 股股票获取。"""
    _require_supported_python()
    ak = _import_akshare()

    errors: list[str] = []
    try:
        return ak.fund_etf_hist_min_em(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            adjust="" if period == "1" else "qfq",
        )
    except Exception as exc:
        errors.append(f"ETF 分钟线接口失败：{exc}")

    try:
        return ak.stock_zh_a_hist_min_em(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            adjust="" if period == "1" else "qfq",
        )
    except Exception as exc:
        errors.append(f"A股分钟线接口失败：{exc}")

    raise RuntimeError(
        "无法获取分钟线数据；分钟线通常只能获取近期数据，1 分钟一般仅支持近 5 个交易日；" + "；".join(errors)
    )


def fetch_daily_data(
    symbol: str,
    start_date: str,
    end_date: str,
    frequency: str = "daily",
    use_cache: bool = True,
    cache_dir: Path = DATA_DIR,
) -> pd.DataFrame:
    """获取 A 股或 ETF 的日线或分钟线数据，并返回统一字段的 DataFrame。"""
    symbol = str(symbol).strip()
    if not symbol:
        raise ValueError("证券代码不能为空，例如股票 000001 或 ETF 510300")

    frequency = str(frequency).strip().lower()
    if frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError("frequency 只支持 daily、1、5、15、30、60")

    if frequency == "daily":
        start = normalize_date(start_date)
        end = normalize_date(end_date)
    else:
        start = normalize_datetime(start_date)
        end = normalize_datetime(end_date)

    if start > end:
        raise ValueError("开始日期不能晚于结束日期")

    ensure_dir(cache_dir)
    cache_file = _cache_path(symbol, start, end, frequency, cache_dir)
    if use_cache and cache_file.exists():
        try:
            df = _read_cache_file(cache_file)
            return df
        except Exception:
            cache_file.unlink(missing_ok=True)

    if use_cache:
        compatible_cache = _find_best_compatible_cache(symbol, start, end, frequency, cache_dir)
        if compatible_cache is not None:
            compatible_cache.to_csv(cache_file, index=False)
            return compatible_cache

    try:
        if frequency == "daily":
            raw_df = _fetch_daily(symbol, start, end)
            df = _rename_columns(raw_df, mode="日线")
        else:
            raw_df = _fetch_minute(symbol, start, end, frequency)
            df = _rename_columns(raw_df, mode="分钟线")
    except Exception as exc:
        if use_cache:
            compatible_cache = _find_best_compatible_cache(symbol, start, end, frequency, cache_dir)
            if compatible_cache is not None:
                compatible_cache.to_csv(cache_file, index=False)
                return compatible_cache
        raise exc

    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=STANDARD_COLUMNS).sort_values("date").reset_index(drop=True)
    if df.empty:
        if frequency == "daily":
            raise ValueError("获取到的日线数据为空，请检查代码、日期区间或网络连接")
        raise ValueError("获取到的分钟线数据为空，请检查代码、时间区间或网络连接")

    if use_cache:
        df.to_csv(cache_file, index=False)
    return df
