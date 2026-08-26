"""Completed order history and estimated P/L API routes."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from yaml import YAMLError

from krakendca import config_store
from krakendca.kraken_client import KrakenClient
from krakendca.order_history import (
    HistoryChartPoint,
    HistorySummary,
    OrderHistoryEntry,
    PairHistorySummary,
    PortfolioHistorySummary,
    apply_live_prices,
    build_history_chart,
    load_order_history,
    summarize_order_history,
)
from krakendca.order_history_import import (
    MAX_IMPORT_TXIDS,
    ImportPreviewItem,
    import_order_history_rows,
    parse_txids,
    preview_order_import,
)
from krakendca.web import auth
from krakendca.web.config_loading import load_config_preserving_root
from krakendca.web.schemas import ApiException, json_object_body, ok

router = APIRouter(tags=["history"])

_YAML_PARSE_ERROR = "Config YAML is malformed."
_CONFIG_ROOT_ERROR = "Config YAML root must be an object."
_LIVE_PRICE_UNAVAILABLE = "Live Kraken price unavailable."
_PUBLIC_ENV_VAR = "KRAKEN_API_PUBLIC_KEY"
_PRIVATE_ENV_VAR = "KRAKEN_API_PRIVATE_KEY"


@router.post("/api/history/import/preview")
async def preview_history_import(request: Request):
    auth.require_csrf(request)
    payload = await json_object_body(request)
    txids = _validate_txid_list(payload.get("txids"), "txids")
    config = _load_normalized_config(request.app.state.config_path)
    public_key, private_key = _effective_kraken_credentials(config)

    kraken_orders = _query_kraken_orders(public_key, private_key, txids)
    items = _preview_import_items(
        txids,
        kraken_orders,
        config,
        request.app.state.config_path,
    )
    return ok(_serialize_import_response(items, 0, 0))


@router.post("/api/history/import")
async def import_history(request: Request):
    auth.require_csrf(request)
    payload = await json_object_body(request)
    txids = _validate_txid_list(payload.get("txids"), "txids")
    selected_txids = set(
        _validate_txid_list(
            payload.get("selected_txids"),
            "selected_txids",
            allow_empty=True,
        )
    )
    config = _load_normalized_config(request.app.state.config_path)
    public_key, private_key = _effective_kraken_credentials(config)

    kraken_orders = _query_kraken_orders(public_key, private_key, txids)
    items = _preview_import_items(
        txids,
        kraken_orders,
        config,
        request.app.state.config_path,
    )
    try:
        result = import_order_history_rows(items, selected_txids)
    except ValueError as exc:
        raise ApiException(
            500,
            "history_import_failed",
            "Order history import failed.",
            details={"message": str(exc)},
        ) from exc

    return ok(
        _serialize_import_response(
            result.items,
            result.imported_count,
            result.skipped_count,
        )
    )


@router.get("/api/history")
async def get_history(request: Request):
    auth.require_authenticated_session(request)
    config = _load_normalized_config(request.app.state.config_path)
    entries = _load_config_order_entries(config, request.app.state.config_path)
    summary = summarize_order_history(entries)
    chart = build_history_chart(entries)
    valuation = {"status": "not_available", "message": None}

    if summary.pairs:
        try:
            prices = _fetch_pair_prices(config, list(summary.pairs))
            if prices:
                summary = apply_live_prices(summary, prices)
                valuation = {"status": "live", "message": None}
        except Exception:
            valuation = {
                "status": "unavailable",
                "message": _LIVE_PRICE_UNAVAILABLE,
            }

    return ok(
        {
            "entries": [_serialize_entry(entry) for entry in entries],
            "pairs": [
                _serialize_pair_summary(summary.pairs[pair])
                for pair in sorted(summary.pairs)
            ],
            "portfolio": _serialize_portfolio_summary(summary.portfolio),
            "chart": [_serialize_chart_point(point) for point in chart],
            "valuation": valuation,
        }
    )


def _load_normalized_config(config_path: str) -> dict:
    try:
        loaded = load_config_preserving_root(config_path)
    except FileNotFoundError as exc:
        raise ApiException(
            400,
            "validation_error",
            "Config file not found.",
            fields={"config": "Config file not found."},
        ) from exc
    except YAMLError as exc:
        raise ApiException(
            400,
            "validation_error",
            _YAML_PARSE_ERROR,
            fields={"config": _YAML_PARSE_ERROR},
        ) from exc

    if not isinstance(loaded, dict):
        raise ApiException(
            400,
            "validation_error",
            _CONFIG_ROOT_ERROR,
            fields={"config": _CONFIG_ROOT_ERROR},
        )

    try:
        return config_store.validate_config(loaded)
    except config_store.ConfigValidationError as exc:
        raise ApiException(
            400,
            "validation_error",
            str(exc),
            fields=exc.fields,
        ) from exc


def _validate_txid_list(
    value: Any,
    field: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ApiException(
            400,
            "validation_error",
            f"{field} must be a list of Kraken order IDs.",
            fields={field: f"{field} must be a list of Kraken order IDs."},
        )

    parsed = parse_txids("\n".join(value))
    fields = {f"{field}.{txid}": message for txid, message in parsed.errors.items()}
    if not parsed.txids and not allow_empty:
        fields[field] = "Please provide at least one Kraken order ID."
    if len(parsed.txids) > MAX_IMPORT_TXIDS:
        fields[field] = f"Please provide no more than {MAX_IMPORT_TXIDS} order IDs."
    if fields:
        raise ApiException(
            400,
            "validation_error",
            "History import request is invalid.",
            fields=fields,
        )
    return parsed.txids


def _effective_kraken_credentials(config: dict) -> tuple[str, str]:
    api = config.get("api") or {}
    public_key = api.get("public_key")
    if public_key is None:
        public_key = os.environ.get(_PUBLIC_ENV_VAR)
    private_key = api.get("private_key")
    if private_key is None:
        private_key = os.environ.get(_PRIVATE_ENV_VAR)

    fields = {}
    if not public_key:
        fields["api.public_key"] = "Please provide your Kraken API public key."
    if not private_key:
        fields["api.private_key"] = "Please provide your Kraken API private key."
    if fields:
        raise ApiException(
            400,
            "validation_error",
            "Kraken API credentials are required.",
            fields=fields,
        )
    return str(public_key), str(private_key)


def _query_kraken_orders(
    public_key: str,
    private_key: str,
    txids: list[str],
) -> dict:
    try:
        return KrakenClient(public_key, private_key).query_orders(txids)
    except (ConnectionError, ValueError) as exc:
        raise ApiException(
            502,
            "kraken_error",
            "Kraken order lookup failed.",
            details={"message": str(exc)},
        ) from exc


def _preview_import_items(
    txids: list[str],
    kraken_orders: dict,
    config: dict,
    config_path: str,
) -> list[ImportPreviewItem]:
    try:
        return preview_order_import(
            txids,
            kraken_orders,
            config,
            config_path,
        )
    except ValueError as exc:
        raise ApiException(
            500,
            "history_read_failed",
            "Order history could not be read.",
            details={"message": str(exc)},
        ) from exc


def _serialize_import_response(
    items: list[ImportPreviewItem],
    imported_count: int,
    skipped_count: int,
) -> dict[str, Any]:
    return {
        "items": [_serialize_import_item(item) for item in items],
        "imported_count": imported_count,
        "skipped_count": skipped_count,
    }


def _serialize_import_item(item: ImportPreviewItem) -> dict[str, Any]:
    return {
        "txid": item.txid,
        "status": item.status,
        "message": item.message,
        "row": item.row,
        "target_file": (
            item.target_path.name if item.target_path is not None else None
        ),
    }


def _load_config_order_entries(config: dict, config_path: str):
    entries: list[OrderHistoryEntry] = []
    config_dir = Path(config_path).parent
    for orders_path in _configured_history_paths(config, config_dir):
        try:
            entries.extend(load_order_history(orders_path))
        except ValueError as exc:
            raise ApiException(
                500,
                "history_read_failed",
                "Order history could not be read.",
                details={"message": str(exc)},
            ) from exc
    return sorted(entries, key=lambda entry: entry.date, reverse=True)


def _configured_history_paths(config: dict, config_dir: Path) -> list[Path]:
    filenames = []
    default_filename = config.get("orders_filepath", "orders.csv")
    for pair_config in config.get("dca_pairs") or []:
        filenames.append(pair_config.get("orders_filepath", default_filename))

    paths = []
    seen = set()
    for filename in filenames:
        path = config_dir / filename
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def _fetch_pair_prices(config: dict, pairs: list[str]) -> dict[str, Decimal]:
    api = config.get("api") or {}
    client = KrakenClient(
        api.get("public_key") or "",
        api.get("private_key") or "",
    )
    prices = {}
    for pair in pairs:
        ticker = client.get_pair_ticker(pair)
        prices[pair] = _ticker_price(ticker, pair)
    return prices


def _ticker_price(ticker: dict, pair: str) -> Decimal:
    result = ticker.get(pair)
    if result is None and ticker:
        result = next(iter(ticker.values()))
    if not isinstance(result, dict):
        raise ValueError("Ticker response did not include pair data.")
    close = result.get("c")
    if not isinstance(close, list) or not close:
        raise ValueError("Ticker response did not include last trade price.")
    return Decimal(str(close[0]))


def _serialize_entry(entry: OrderHistoryEntry) -> dict[str, Any]:
    return {
        "date": entry.date.isoformat(),
        "pair": entry.pair,
        "type": entry.type,
        "order_type": entry.order_type,
        "o_flags": entry.o_flags,
        "pair_price": _decimal(entry.pair_price),
        "volume": _decimal(entry.volume),
        "price": _decimal(entry.price),
        "fee": _decimal(entry.fee),
        "total_price": _decimal(entry.total_price),
        "txid": entry.txid,
        "description": entry.description,
    }


def _serialize_pair_summary(summary: PairHistorySummary) -> dict[str, Any]:
    return {
        "pair": summary.pair,
        "trade_count": summary.trade_count,
        "total_volume": _decimal(summary.total_volume),
        "total_spent": _decimal(summary.total_spent),
        "total_price": _decimal(summary.total_price),
        "total_fees": _decimal(summary.total_fees),
        "average_buy_price": _optional_decimal(summary.average_buy_price),
        "last_trade_at": (
            summary.last_trade_at.isoformat()
            if summary.last_trade_at is not None
            else None
        ),
        "last_trade_txid": summary.last_trade_txid,
        "current_price": _optional_decimal(summary.current_price),
        "estimated_value": _optional_decimal(summary.estimated_value),
        "estimated_pl": _optional_decimal(summary.estimated_pl),
    }


def _serialize_portfolio_summary(
    summary: PortfolioHistorySummary,
) -> dict[str, Any]:
    return {
        "trade_count": summary.trade_count,
        "total_spent": _decimal(summary.total_spent),
        "total_price": _decimal(summary.total_price),
        "total_fees": _decimal(summary.total_fees),
        "estimated_value": _optional_decimal(summary.estimated_value),
        "estimated_pl": _optional_decimal(summary.estimated_pl),
    }


def _serialize_chart_point(point: HistoryChartPoint) -> dict[str, Any]:
    return {
        "date": point.date.isoformat(),
        "pair": point.pair,
        "txid": point.txid,
        "spent": _decimal(point.spent),
        "volume": _decimal(point.volume),
        "cumulative_spent": _decimal(point.cumulative_spent),
        "cumulative_volume": _decimal(point.cumulative_volume),
    }


def _optional_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return _decimal(value)


def _decimal(value: Decimal) -> str:
    return format(value, "f")
