from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    """确保目录存在，避免保存缓存或图片时因目录缺失报错。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise RuntimeError(f"创建目录失败：{path}，原因：{exc}") from exc


def normalize_date(date_value: str) -> str:
    """校验并标准化日期，只接受 YYYYMMDD 格式。"""
    try:
        return datetime.strptime(str(date_value), "%Y%m%d").strftime("%Y%m%d")
    except Exception as exc:
        raise ValueError(f"日期格式错误：{date_value}，请使用 YYYYMMDD，例如 20230101") from exc


def normalize_datetime(datetime_value: str) -> str:
    """校验并标准化日期时间，只接受 YYYY-MM-DD HH:MM:SS 格式。"""
    try:
        return datetime.strptime(str(datetime_value), "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        raise ValueError(
            f"日期时间格式错误：{datetime_value}，请使用 YYYY-MM-DD HH:MM:SS，例如 2026-05-08 09:30:00"
        ) from exc


def friendly_error(message: str, exc: Exception) -> str:
    """把底层异常包装成适合展示给新手用户的提示。"""
    return f"{message}\n详细原因：{exc}"


def format_percent(value: Any) -> str:
    """把小数收益率格式化成百分比文本。"""
    try:
        return f"{float(value) * 100:.2f}%"
    except Exception:
        return "N/A"
