"""Completed order history and estimated P/L API routes."""

from __future__ import annotations

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
from krakendca.web import auth
from krakendca.web.config_loading import load_config_preserving_root
from krakendca.web.schemas import ApiException, ok

router = APIRouter(tags=["history"])

_YAML_PARSE_ERROR = "Config YAML is malformed."
_CONFIG_ROOT_ERROR = "Config YAML root must be an object."
_LIVE_PRICE_UNAVAILABLE = "Live Kraken price unavailable."


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
