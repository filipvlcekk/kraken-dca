"""Order history import core tests."""

from __future__ import annotations

import csv
from datetime import datetime

import pytest

from krakendca.order import Order
from krakendca.order_history_csv import ORDER_HISTORY_FILE_LOCKS
from krakendca.order_history_import import (
    ImportPreviewItem,
    ORDER_HISTORY_FIELDNAMES,
    import_order_history_rows,
    preview_order_import,
)
from krakendca.order_history_import import parse_txids


READY_TXID = "OCYS4K-OILOE-36HPAE"
SECOND_TXID = "O4OHPN-MU47M-3FUXEV"


def _config(
    *,
    pair: str = "XETHZEUR",
    pair_orders_filepath: str | None = None,
) -> dict:
    pair_config = {"pair": pair}
    if pair_orders_filepath is not None:
        pair_config["orders_filepath"] = pair_orders_filepath
    return {"orders_filepath": "orders.csv", "dca_pairs": [pair_config]}


def _kraken_order(
    *,
    status: str = "closed",
    pair: str = "XETHZEUR",
    configured_pair: str | None = None,
    order_type: str = "buy",
    ordertype: str = "limit",
    price: str | None = "2083.16",
    vol_exec: str | None = "0.01",
    cost: str | None = "20.8316",
    fee: str | None = "0.0542",
    oflags: str | None = "fciq",
    closetm: float | str | None = 1720000060.0,
    description: str | None = "buy 0.01 XETHZEUR @ limit 2083.16",
) -> dict:
    descr = {
        "pair": configured_pair or pair,
        "type": order_type,
        "ordertype": ordertype,
        "price": price,
        "order": description,
    }
    return {
        "status": status,
        "descr": descr,
        "opentm": 1720000000.0,
        "closetm": closetm,
        "vol_exec": vol_exec,
        "cost": cost,
        "fee": fee,
        "oflags": oflags,
    }


def _row(
    *,
    txid: str = READY_TXID,
    pair: str = "XETHZEUR",
) -> dict[str, str]:
    return {
        "date": "2024-07-03T09:47:40",
        "pair": pair,
        "type": "buy",
        "order_type": "limit",
        "o_flags": "fciq",
        "pair_price": "2083.16",
        "volume": "0.01",
        "price": "20.8316",
        "fee": "0.0542",
        "total_price": "20.8858",
        "txid": txid,
        "description": "buy 0.01 XETHZEUR @ limit 2083.16",
    }


def _write_history(path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=ORDER_HISTORY_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _read_history(path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def _ready_item(tmp_path, *, txid: str = READY_TXID) -> ImportPreviewItem:
    return ImportPreviewItem(
        txid=txid,
        status="ready",
        row=_row(txid=txid),
        target_path=tmp_path / "orders.csv",
    )


def _targeted_ready_item(path, *, txid: str = READY_TXID) -> ImportPreviewItem:
    return ImportPreviewItem(
        txid=txid,
        status="ready",
        row=_row(txid=txid),
        target_path=path,
    )


def test_parse_txids_accepts_lines_commas_and_deduplicates() -> None:
    result = parse_txids(
        "OCYS4K-OILOE-36HPAE\nO4OHPN-MU47M-3FUXEV, OCYS4K-OILOE-36HPAE"
    )

    assert result.txids == ["OCYS4K-OILOE-36HPAE", "O4OHPN-MU47M-3FUXEV"]
    assert result.errors == {}


def test_parse_txids_rejects_malformed_ids() -> None:
    result = parse_txids("not-an-order")

    assert result.txids == []
    assert result.errors == {"not-an-order": "Invalid Kraken order ID."}


def test_preview_marks_closed_buy_limit_order_ready_with_exact_row(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _config()

    item = preview_order_import(
        [READY_TXID],
        {READY_TXID: _kraken_order()},
        config,
        str(config_path),
    )[0]

    assert item.status == "ready"
    assert item.message is None
    assert item.target_path == tmp_path / "orders.csv"
    assert item.row is not None
    assert list(item.row) == ORDER_HISTORY_FIELDNAMES
    assert item.row == {
        "date": "2024-07-03T09:47:40",
        "pair": "XETHZEUR",
        "type": "buy",
        "order_type": "limit",
        "o_flags": "fciq",
        "pair_price": "2083.16",
        "volume": "0.01",
        "price": "20.8316",
        "fee": "0.0542",
        "total_price": "20.8858",
        "txid": READY_TXID,
        "description": "buy 0.01 XETHZEUR @ limit 2083.16",
    }


def test_preview_uses_pair_level_orders_filepath(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config = _config(pair_orders_filepath="xeth-orders.csv")

    item = preview_order_import(
        [READY_TXID],
        {READY_TXID: _kraken_order()},
        config,
        str(config_path),
    )[0]

    assert item.status == "ready"
    assert item.target_path == tmp_path / "xeth-orders.csv"


def test_preview_marks_existing_txid_already_imported(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_history(tmp_path / "orders.csv", [_row(txid=READY_TXID)])

    item = preview_order_import(
        [READY_TXID],
        {READY_TXID: _kraken_order()},
        _config(),
        str(config_path),
    )[0]

    assert item.status == "already_imported"
    assert item.row is None
    assert item.target_path == tmp_path / "orders.csv"


def test_preview_classifies_not_found_and_not_closed(tmp_path) -> None:
    items = preview_order_import(
        [READY_TXID, SECOND_TXID],
        {SECOND_TXID: _kraken_order(status="open")},
        _config(),
        str(tmp_path / "config.yaml"),
    )

    assert [item.status for item in items] == ["not_found", "not_closed"]


@pytest.mark.parametrize(
    ("order", "message"),
    [
        (_kraken_order(order_type="sell"), "only buy orders"),
        (_kraken_order(ordertype="market"), "only limit orders"),
        (_kraken_order(pair="XXBTZEUR"), "not configured"),
        (_kraken_order(cost=None), "missing required field: cost"),
        (_kraken_order(fee=None), "missing required field: fee"),
        (_kraken_order(vol_exec=None), "missing required field: vol_exec"),
        (_kraken_order(description=None), "missing required field: descr.order"),
    ],
)
def test_preview_marks_unsupported_orders(tmp_path, order, message) -> None:
    item = preview_order_import(
        [READY_TXID],
        {READY_TXID: order},
        _config(),
        str(tmp_path / "config.yaml"),
    )[0]

    assert item.status == "unsupported"
    assert item.row is None
    assert message in item.message


def test_preview_sanitizes_kraken_derived_formula_strings(tmp_path) -> None:
    item = preview_order_import(
        [READY_TXID],
        {
            READY_TXID: _kraken_order(
                pair="=XETHZEUR",
                configured_pair="=XETHZEUR",
                oflags="+fciq",
                price="-2083.16",
                description="@malicious",
            )
        },
        _config(pair="=XETHZEUR"),
        str(tmp_path / "config.yaml"),
    )[0]

    assert item.status == "ready"
    assert item.row is not None
    assert item.row["pair"] == "'=XETHZEUR"
    assert item.row["o_flags"] == "'+fciq"
    assert item.row["pair_price"] == "'-2083.16"
    assert item.row["description"] == "'@malicious"


def test_preview_marks_malformed_timestamp_unsupported(tmp_path) -> None:
    item = preview_order_import(
        [READY_TXID],
        {READY_TXID: _kraken_order(closetm="not-a-timestamp")},
        _config(),
        str(tmp_path / "config.yaml"),
    )[0]

    assert item.status == "unsupported"
    assert item.row is None
    assert "invalid timestamp" in item.message


def test_import_and_order_save_use_shared_default_file_lock(tmp_path) -> None:
    target = tmp_path / "orders.csv"
    lock = _TrackingLock()
    ORDER_HISTORY_FILE_LOCKS[target] = lock
    try:
        order = Order(
            datetime.strptime("2021-04-15 21:33:28", "%Y-%m-%d %H:%M:%S"),
            "XETHZEUR",
            "buy",
            "limit",
            "fciq",
            2083.16,
            0.00957589,
            19.9481,
            0.0519,
            20.0,
        )
        order.txid = SECOND_TXID
        order.description = "buy 0.00957589 ETHEUR @ limit 2083.16"

        order.save_order_csv(str(target))
        import_order_history_rows([_ready_item(tmp_path)], {READY_TXID})
    finally:
        ORDER_HISTORY_FILE_LOCKS.pop(target, None)

    assert lock.acquired == 2
    assert lock.released == 2


def test_import_creates_missing_csv_with_exact_header(tmp_path) -> None:
    target = tmp_path / "orders.csv"

    result = import_order_history_rows(
        [_ready_item(tmp_path)],
        {READY_TXID},
        {},
    )

    assert result.imported_count == 1
    assert result.skipped_count == 0
    with target.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file)
        assert next(reader) == ORDER_HISTORY_FIELDNAMES
    assert _read_history(target) == [_row(txid=READY_TXID)]


def test_import_appends_to_existing_valid_csv(tmp_path) -> None:
    target = tmp_path / "orders.csv"
    _write_history(target, [_row(txid=SECOND_TXID)])

    result = import_order_history_rows(
        [_ready_item(tmp_path)],
        {READY_TXID},
        {},
    )

    assert result.imported_count == 1
    assert result.skipped_count == 0
    assert [row["txid"] for row in _read_history(target)] == [
        SECOND_TXID,
        READY_TXID,
    ]


def test_import_rejects_malformed_existing_header(tmp_path) -> None:
    target = tmp_path / "orders.csv"
    target.write_text("bad,header\nvalue,value\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected columns"):
        import_order_history_rows([_ready_item(tmp_path)], {READY_TXID}, {})

    assert target.read_text(encoding="utf-8") == "bad,header\nvalue,value\n"


def test_import_rechecks_duplicates_under_write_path(tmp_path) -> None:
    target = tmp_path / "orders.csv"
    ready_item = _ready_item(tmp_path)
    _write_history(target, [_row(txid=READY_TXID)])

    result = import_order_history_rows([ready_item], {READY_TXID}, {})

    assert result.imported_count == 0
    assert result.skipped_count == 1
    assert [row["txid"] for row in _read_history(target)] == [READY_TXID]


def test_import_validates_all_target_files_before_writing_any_row(tmp_path) -> None:
    valid_target = tmp_path / "orders.csv"
    malformed_target = tmp_path / "bad-orders.csv"
    malformed_target.write_text("wrong\n", encoding="utf-8")
    ready_items = [
        _targeted_ready_item(valid_target, txid=READY_TXID),
        _targeted_ready_item(malformed_target, txid=SECOND_TXID),
    ]

    with pytest.raises(ValueError, match="unexpected columns"):
        import_order_history_rows(
            ready_items,
            {READY_TXID, SECOND_TXID},
            {},
        )

    assert not valid_target.exists()
    assert malformed_target.read_text(encoding="utf-8") == "wrong\n"


class _TrackingLock:
    def __init__(self) -> None:
        self.acquired = 0
        self.released = 0

    def acquire(self) -> None:
        self.acquired += 1

    def release(self) -> None:
        self.released += 1
