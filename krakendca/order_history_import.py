"""Import completed Kraken orders into local CSV order history."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import MutableMapping

from krakendca.order_history_csv import (
    ORDER_HISTORY_FIELDNAMES,
    append_order_history_row,
    order_history_file_lock,
    order_history_lock_path,
    read_order_history_txids,
    sanitize_csv_value,
    validate_order_history_writable,
)

ORDER_TXID_PATTERN = re.compile(r"^[A-Z0-9]{6}-[A-Z0-9]{5}-[A-Z0-9]{6}$")
MAX_IMPORT_TXIDS = 50


@dataclass(frozen=True)
class TxidParseResult:
    txids: list[str]
    errors: dict[str, str]


@dataclass(frozen=True)
class ImportPreviewItem:
    txid: str
    status: str
    message: str | None = None
    row: dict[str, str] | None = None
    target_path: Path | None = None


@dataclass(frozen=True)
class ImportResult:
    imported_count: int
    skipped_count: int
    items: list[ImportPreviewItem]


def parse_txids(text: str) -> TxidParseResult:
    """Parse newline or comma separated Kraken order IDs."""
    txids = []
    errors = {}
    seen = set()
    for raw_item in re.split(r"[\n,]", text):
        item = raw_item.strip()
        if not item:
            continue
        if not ORDER_TXID_PATTERN.match(item):
            errors[item] = "Invalid Kraken order ID."
            continue
        if item not in seen:
            txids.append(item)
            seen.add(item)
    return TxidParseResult(txids=txids, errors=errors)


def preview_order_import(
    txids: list[str],
    kraken_orders: dict,
    config: dict,
    config_path: str,
) -> list[ImportPreviewItem]:
    """Classify requested Kraken orders before CSV import."""
    config_dir = Path(config_path).parent
    pair_targets = _configured_pair_targets(config, config_dir)
    existing_txids = _existing_history_txids(pair_targets.values())

    items = []
    for txid in txids:
        target_path = None
        if txid in existing_txids:
            target_path = existing_txids[txid]
            items.append(
                ImportPreviewItem(
                    txid=txid,
                    status="already_imported",
                    target_path=target_path,
                )
            )
            continue

        order = kraken_orders.get(txid)
        if order is None:
            items.append(
                ImportPreviewItem(
                    txid=txid,
                    status="not_found",
                    message="Kraken did not return this order ID.",
                )
            )
            continue

        if order.get("status") != "closed":
            items.append(
                ImportPreviewItem(
                    txid=txid,
                    status="not_closed",
                    message="Order is not closed.",
                )
            )
            continue

        item = _preview_closed_order(txid, order, pair_targets)
        items.append(item)

    return items


def import_order_history_rows(
    items: list[ImportPreviewItem],
    selected_txids: set[str],
    locks: MutableMapping[Path, threading.Lock] | None = None,
) -> ImportResult:
    """Append selected ready preview rows into their target CSV files."""
    selected_ready_items = [
        item
        for item in items
        if item.txid in selected_txids
        and item.status == "ready"
        and item.row is not None
        and item.target_path is not None
    ]
    target_paths_by_lock_path = {}
    for item in selected_ready_items:
        assert item.target_path is not None
        target_paths_by_lock_path.setdefault(
            order_history_lock_path(item.target_path),
            item.target_path,
        )
    target_paths = sorted(
        target_paths_by_lock_path.items(),
        key=lambda path_item: str(path_item[0]),
    )
    acquired_locks = []
    try:
        for lock_path, _path in target_paths:
            lock = order_history_file_lock(lock_path, locks)
            lock.acquire()
            acquired_locks.append(lock)

        existing_by_path = {
            lock_path: read_order_history_txids(path)
            for lock_path, path in target_paths
        }
        for _lock_path, path in target_paths:
            validate_order_history_writable(path)

        imported_count = 0
        skipped_count = 0
        for item in selected_ready_items:
            assert item.row is not None
            assert item.target_path is not None
            lock_path = order_history_lock_path(item.target_path)
            existing_txids = existing_by_path[lock_path]
            if item.txid in existing_txids:
                skipped_count += 1
                continue
            append_order_history_row(item.target_path, item.row)
            existing_txids.add(item.txid)
            imported_count += 1
        return ImportResult(
            imported_count=imported_count,
            skipped_count=skipped_count,
            items=items,
        )
    finally:
        for lock in reversed(acquired_locks):
            lock.release()


def _preview_closed_order(
    txid: str,
    order: dict,
    pair_targets: dict[str, tuple[str, Path]],
) -> ImportPreviewItem:
    descr = order.get("descr")
    if not isinstance(descr, dict):
        return _unsupported(txid, "missing required field: descr")

    missing = _missing_required_fields(order, descr)
    if missing:
        return _unsupported(txid, f"missing required field: {missing}")

    if descr["type"] != "buy":
        return _unsupported(
            txid,
            "unsupported order: only buy orders can be imported.",
        )
    if descr["ordertype"] != "limit":
        return _unsupported(
            txid,
            "unsupported order: only limit orders can be imported.",
        )

    pair_match = pair_targets.get(str(descr["pair"]))
    if pair_match is None:
        return _unsupported(
            txid,
            f"unsupported order: pair {descr['pair']} is not configured.",
        )
    configured_pair, target_path = pair_match

    try:
        total_price = str(
            Decimal(str(order["cost"])) + Decimal(str(order["fee"]))
        )
    except InvalidOperation:
        return _unsupported(txid, "unsupported order: invalid cost or fee.")

    try:
        order_date = _order_date(order)
    except (OverflowError, TypeError, ValueError):
        return _unsupported(txid, "unsupported order: invalid timestamp.")

    row = {
        "date": order_date,
        "pair": configured_pair,
        "type": str(descr["type"]),
        "order_type": str(descr["ordertype"]),
        "o_flags": (
            ""
            if order.get("oflags") is None
            else str(order.get("oflags"))
        ),
        "pair_price": str(descr["price"]),
        "volume": str(order["vol_exec"]),
        "price": str(order["cost"]),
        "fee": str(order["fee"]),
        "total_price": total_price,
        "txid": txid,
        "description": str(descr["order"]),
    }
    sanitized_row = {
        field: str(sanitize_csv_value(value))
        for field, value in row.items()
    }
    return ImportPreviewItem(
        txid=txid,
        status="ready",
        row=sanitized_row,
        target_path=target_path,
    )


def _missing_required_fields(order: dict, descr: dict) -> str | None:
    for field in ("pair", "type", "ordertype", "price", "order"):
        if descr.get(field) in (None, ""):
            return f"descr.{field}"
    for field in ("vol_exec", "cost", "fee"):
        if order.get(field) in (None, ""):
            return field
    if (
        order.get("closetm") in (None, "")
        and order.get("opentm") in (None, "")
    ):
        return "closetm"
    return None


def _order_date(order: dict) -> str:
    timestamp = order.get("closetm", order.get("opentm"))
    if timestamp in (None, ""):
        timestamp = order.get("opentm")
    return datetime.fromtimestamp(
        float(timestamp),
        UTC,
    ).replace(tzinfo=None).isoformat()


def _unsupported(txid: str, message: str) -> ImportPreviewItem:
    return ImportPreviewItem(txid=txid, status="unsupported", message=message)


def _configured_pair_targets(
    config: dict,
    config_dir: Path,
) -> dict[str, tuple[str, Path]]:
    default_filename = config.get("orders_filepath", "orders.csv")
    targets = {}
    for pair_config in config.get("dca_pairs") or []:
        configured_pair = str(pair_config.get("pair", ""))
        if not configured_pair:
            continue
        target_path = config_dir / pair_config.get(
            "orders_filepath",
            default_filename,
        )
        for alias in _pair_aliases(pair_config):
            targets[alias] = (configured_pair, target_path)
    return targets


def _pair_aliases(pair_config: dict) -> set[str]:
    aliases = set()
    for key in ("pair", "altname", "alt_name", "wsname"):
        value = pair_config.get(key)
        if isinstance(value, str) and value:
            aliases.add(value)
    return aliases


def _existing_history_txids(paths) -> dict[str, Path]:
    txids = {}
    for _configured_pair, path in set(paths):
        for txid in read_order_history_txids(path):
            txids[txid] = path
    return txids
