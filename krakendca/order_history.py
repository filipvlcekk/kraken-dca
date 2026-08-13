"""Read and summarize completed DCA order history CSV files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

_REQUIRED_FIELDS = {
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
}


@dataclass(frozen=True)
class OrderHistoryEntry:
    date: datetime
    pair: str
    type: str
    order_type: str
    o_flags: str
    pair_price: Decimal
    volume: Decimal
    price: Decimal
    fee: Decimal
    total_price: Decimal
    txid: str
    description: str


@dataclass(frozen=True)
class PairHistorySummary:
    pair: str
    trade_count: int
    total_volume: Decimal
    total_spent: Decimal
    total_price: Decimal
    total_fees: Decimal
    average_buy_price: Decimal | None
    last_trade_at: datetime | None
    last_trade_txid: str | None
    current_price: Decimal | None = None
    estimated_value: Decimal | None = None
    estimated_pl: Decimal | None = None


@dataclass(frozen=True)
class PortfolioHistorySummary:
    trade_count: int
    total_spent: Decimal
    total_price: Decimal
    total_fees: Decimal
    estimated_value: Decimal | None = None
    estimated_pl: Decimal | None = None


@dataclass(frozen=True)
class HistorySummary:
    pairs: dict[str, PairHistorySummary]
    portfolio: PortfolioHistorySummary


@dataclass(frozen=True)
class HistoryChartPoint:
    date: datetime
    pair: str
    txid: str
    spent: Decimal
    volume: Decimal
    cumulative_spent: Decimal
    cumulative_volume: Decimal


def load_order_history(path: Path | str) -> list[OrderHistoryEntry]:
    """Load completed order rows, newest first."""
    history_path = Path(path)
    if not history_path.exists():
        return []

    try:
        with history_path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            _validate_header(reader.fieldnames)
            entries = [_entry_from_row(row) for row in reader]
    except (csv.Error, OSError, ValueError) as exc:
        raise ValueError(f"Can't read order history -> {exc}") from exc

    return sorted(entries, key=lambda entry: entry.date, reverse=True)


def summarize_order_history(
    entries: list[OrderHistoryEntry],
) -> HistorySummary:
    """Build per-pair and portfolio totals from completed order entries."""
    summaries = {}
    for pair in sorted({entry.pair for entry in entries}):
        pair_entries = [entry for entry in entries if entry.pair == pair]
        total_volume = sum(
            (entry.volume for entry in pair_entries), Decimal("0")
        )
        total_price = sum((entry.price for entry in pair_entries), Decimal("0"))
        total_fees = sum((entry.fee for entry in pair_entries), Decimal("0"))
        total_spent = sum(
            (entry.total_price for entry in pair_entries), Decimal("0")
        )
        newest = max(pair_entries, key=lambda entry: entry.date)
        average_buy_price = (
            total_price / total_volume if total_volume != 0 else None
        )
        summaries[pair] = PairHistorySummary(
            pair=pair,
            trade_count=len(pair_entries),
            total_volume=total_volume,
            total_spent=total_spent,
            total_price=total_price,
            total_fees=total_fees,
            average_buy_price=average_buy_price,
            last_trade_at=newest.date,
            last_trade_txid=newest.txid,
        )

    portfolio = PortfolioHistorySummary(
        trade_count=sum(summary.trade_count for summary in summaries.values()),
        total_spent=sum(
            (summary.total_spent for summary in summaries.values()),
            Decimal("0"),
        ),
        total_price=sum(
            (summary.total_price for summary in summaries.values()),
            Decimal("0"),
        ),
        total_fees=sum(
            (summary.total_fees for summary in summaries.values()),
            Decimal("0"),
        ),
    )
    return HistorySummary(pairs=summaries, portfolio=portfolio)


def build_history_chart(
    entries: list[OrderHistoryEntry],
) -> list[HistoryChartPoint]:
    """Build chronological accumulation points from completed buys."""
    cumulative_spent = Decimal("0")
    cumulative_volume = Decimal("0")
    points = []
    for entry in sorted(entries, key=lambda item: item.date):
        cumulative_spent += entry.total_price
        cumulative_volume += entry.volume
        points.append(
            HistoryChartPoint(
                date=entry.date,
                pair=entry.pair,
                txid=entry.txid,
                spent=entry.total_price,
                volume=entry.volume,
                cumulative_spent=cumulative_spent,
                cumulative_volume=cumulative_volume,
            )
        )
    return points


def apply_live_prices(
    summary: HistorySummary,
    prices: dict[str, Decimal],
) -> HistorySummary:
    """Return a copy of history summaries enriched with live price estimates."""
    pairs = {}
    portfolio_value = Decimal("0")
    for pair, pair_summary in summary.pairs.items():
        current_price = prices.get(pair)
        estimated_value = None
        estimated_pl = None
        if current_price is not None:
            estimated_value = pair_summary.total_volume * current_price
            estimated_pl = estimated_value - pair_summary.total_spent
            portfolio_value += estimated_value
        pairs[pair] = PairHistorySummary(
            **{
                **pair_summary.__dict__,
                "current_price": current_price,
                "estimated_value": estimated_value,
                "estimated_pl": estimated_pl,
            }
        )

    portfolio_pl = (
        portfolio_value - summary.portfolio.total_spent if prices else None
    )
    portfolio_value_value = portfolio_value if prices else None
    portfolio = PortfolioHistorySummary(
        trade_count=summary.portfolio.trade_count,
        total_spent=summary.portfolio.total_spent,
        total_price=summary.portfolio.total_price,
        total_fees=summary.portfolio.total_fees,
        estimated_value=portfolio_value_value,
        estimated_pl=portfolio_pl,
    )
    return HistorySummary(pairs=pairs, portfolio=portfolio)


def _validate_header(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise ValueError("order history has no header")
    missing = _REQUIRED_FIELDS.difference(fieldnames)
    if missing:
        raise ValueError(
            "order history is missing columns: " + ", ".join(sorted(missing))
        )


def _entry_from_row(row: dict[str, str]) -> OrderHistoryEntry:
    return OrderHistoryEntry(
        date=_parse_date(row["date"]),
        pair=row["pair"],
        type=row["type"],
        order_type=row["order_type"],
        o_flags=row["o_flags"],
        pair_price=Decimal(row["pair_price"]),
        volume=Decimal(row["volume"]),
        price=Decimal(row["price"]),
        fee=Decimal(row["fee"]),
        total_price=Decimal(row["total_price"]),
        txid=row["txid"],
        description=row["description"],
    )


def _parse_date(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
