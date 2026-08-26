"""Shared CSV helpers for completed order history files."""

from __future__ import annotations

import csv
import re
import tempfile
import threading
from pathlib import Path
from typing import MutableMapping

ORDER_HISTORY_FIELDNAMES = [
    "date",
    "pair",
    "type",
    "order_type",
    "o_flags",
    "pair_price",
    "volume",
    "price",
    "fee",
    "total_price",
    "txid",
    "description",
]
ORDER_HISTORY_FILE_LOCKS: dict[Path, threading.Lock] = {}


def _normalized_order_history_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def order_history_file_lock(
    path: Path | str,
    locks: MutableMapping[Path, threading.Lock] | None = None,
):
    """Return the process-local lock for an order history CSV path."""
    lock_registry = ORDER_HISTORY_FILE_LOCKS if locks is None else locks
    return lock_registry.setdefault(_normalized_order_history_path(path), threading.Lock())


def sanitize_csv_value(value: object) -> object:
    """Prefix formula-like strings to avoid CSV injection."""
    if isinstance(value, str) and re.match(r"^\s*[=+\-@]", value):
        return f"'{value}"
    return value


def read_order_csv_header(orders_filepath: Path | str) -> list[str]:
    """Read an order history CSV header, returning empty for missing files."""
    try:
        with open(orders_filepath, newline="") as csv_file:
            return next(csv.reader(csv_file), [])
    except FileNotFoundError:
        return []


def validate_exact_header(fieldnames: list[str] | None) -> None:
    """Reject order history CSV files that do not match writer columns."""
    if fieldnames != ORDER_HISTORY_FIELDNAMES:
        raise ValueError("existing order history has unexpected columns")


def read_order_history_txids(path: Path) -> set[str]:
    """Read existing txids from a non-empty order history CSV."""
    if path.exists() and path.is_dir():
        raise ValueError("existing order history has unexpected columns")
    if not path.exists() or path.stat().st_size == 0:
        return set()
    try:
        with path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            validate_exact_header(reader.fieldnames)
            return {
                row.get("txid", "")
                for row in reader
                if row.get("txid")
            }
    except (csv.Error, OSError) as exc:
        raise ValueError(f"Can't read order history -> {exc}") from exc


def validate_order_history_writable(path: Path) -> None:
    """Validate an order history target can be written before importing rows."""
    if path.exists() and path.is_dir():
        raise ValueError("existing order history has unexpected columns")
    if path.exists():
        try:
            with path.open("a", newline="", encoding="utf-8"):
                pass
        except OSError as exc:
            raise ValueError(f"Can't save order history -> {exc}") from exc
        return

    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise ValueError("Can't save order history -> parent directory is not writable")
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{path.name}.",
        ):
            pass
    except OSError as exc:
        raise ValueError(f"Can't save order history -> {exc}") from exc


def append_order_history_row(path: Path, row: dict[str, str]) -> None:
    """Append a row using the exact order history CSV schema."""
    validate_exact_header(list(row))
    write_header = not path.exists() or path.stat().st_size == 0
    mode = "w" if write_header else "a"
    try:
        with path.open(mode, newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=ORDER_HISTORY_FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
    except (csv.Error, OSError) as exc:
        raise ValueError(f"Can't save order history -> {exc}") from exc
