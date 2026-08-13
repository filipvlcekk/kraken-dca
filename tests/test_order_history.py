"""Order history parsing and aggregation tests."""

from __future__ import annotations

import csv
from decimal import Decimal

from krakendca.order_history import (
    apply_live_prices,
    build_history_chart,
    load_order_history,
    summarize_order_history,
)


def test_load_order_history_returns_entries_newest_first(tmp_path) -> None:
    history_path = tmp_path / "orders.csv"
    _write_orders(
        history_path,
        [
            _order_row(
                date="2026-07-20 10:00:00",
                pair="XETHZEUR",
                volume="0.01",
                price="20",
                fee="0.05",
                total_price="20.05",
                txid="OLDER",
            ),
            _order_row(
                date="2026-07-21 10:00:00",
                pair="XETHZEUR",
                volume="0.02",
                price="40",
                fee="0.10",
                total_price="40.10",
                txid="NEWER",
            ),
        ],
    )

    entries = load_order_history(history_path)

    assert [entry.txid for entry in entries] == ["NEWER", "OLDER"]
    assert entries[0].pair == "XETHZEUR"
    assert entries[0].volume == Decimal("0.02")
    assert entries[0].price == Decimal("40")
    assert entries[0].fee == Decimal("0.10")
    assert entries[0].total_price == Decimal("40.10")


def test_load_order_history_returns_empty_for_missing_file(tmp_path) -> None:
    assert load_order_history(tmp_path / "missing.csv") == []


def test_summarize_order_history_groups_by_pair(tmp_path) -> None:
    history_path = tmp_path / "orders.csv"
    _write_orders(
        history_path,
        [
            _order_row(
                date="2026-07-20 10:00:00",
                pair="XETHZEUR",
                volume="0.01",
                price="20",
                fee="0.05",
                total_price="20.05",
                txid="ETH1",
            ),
            _order_row(
                date="2026-07-21 10:00:00",
                pair="XETHZEUR",
                volume="0.02",
                price="40",
                fee="0.10",
                total_price="40.10",
                txid="ETH2",
            ),
            _order_row(
                date="2026-07-22 10:00:00",
                pair="XXBTZEUR",
                volume="0.001",
                price="30",
                fee="0.08",
                total_price="30.08",
                txid="BTC1",
            ),
        ],
    )

    summary = summarize_order_history(load_order_history(history_path))

    eth = summary.pairs["XETHZEUR"]
    assert eth.trade_count == 2
    assert eth.total_volume == Decimal("0.03")
    assert eth.total_spent == Decimal("60.15")
    assert eth.total_fees == Decimal("0.15")
    assert eth.average_buy_price == Decimal("2000")
    assert eth.last_trade_txid == "ETH2"
    assert summary.portfolio.trade_count == 3
    assert summary.portfolio.total_spent == Decimal("90.23")


def test_build_history_chart_accumulates_completed_buys(tmp_path) -> None:
    history_path = tmp_path / "orders.csv"
    _write_orders(
        history_path,
        [
            _order_row(
                date="2026-07-21 10:00:00",
                pair="XETHZEUR",
                volume="0.02",
                price="40",
                fee="0.10",
                total_price="40.10",
                txid="SECOND",
            ),
            _order_row(
                date="2026-07-20 10:00:00",
                pair="XETHZEUR",
                volume="0.01",
                price="20",
                fee="0.05",
                total_price="20.05",
                txid="FIRST",
            ),
        ],
    )

    points = build_history_chart(load_order_history(history_path))

    assert [(point.txid, point.cumulative_spent) for point in points] == [
        ("FIRST", Decimal("20.05")),
        ("SECOND", Decimal("60.15")),
    ]
    assert points[-1].cumulative_volume == Decimal("0.03")


def test_apply_live_prices_calculates_estimated_pl(tmp_path) -> None:
    history_path = tmp_path / "orders.csv"
    _write_orders(
        history_path,
        [
            _order_row(
                pair="XETHZEUR",
                volume="0.03",
                price="60",
                fee="0.15",
                total_price="60.15",
            ),
        ],
    )
    summary = summarize_order_history(load_order_history(history_path))

    valuation = apply_live_prices(summary, {"XETHZEUR": Decimal("2500")})

    eth = valuation.pairs["XETHZEUR"]
    assert eth.current_price == Decimal("2500")
    assert eth.estimated_value == Decimal("75.00")
    assert eth.estimated_pl == Decimal("14.85")
    assert valuation.portfolio.estimated_value == Decimal("75.00")
    assert valuation.portfolio.estimated_pl == Decimal("14.85")


def _write_orders(path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _order_row(
    *,
    date: str = "2026-07-20 10:00:00",
    pair: str,
    volume: str,
    price: str,
    fee: str,
    total_price: str,
    txid: str = "TXID",
) -> dict[str, str]:
    return {
        "date": date,
        "pair": pair,
        "type": "buy",
        "order_type": "limit",
        "o_flags": "fciq",
        "pair_price": "2000",
        "volume": volume,
        "price": price,
        "fee": fee,
        "total_price": total_price,
        "txid": txid,
        "description": f"buy {volume} {pair} @ limit 2000",
    }
