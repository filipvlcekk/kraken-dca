"""runner.py tests module."""
from datetime import datetime

from freezegun import freeze_time

from krakendca.runner import RunResult, run_pair


class FakeKrakenApi:
    """Small Kraken API fake for runner unit tests."""

    def __init__(
        self,
        *,
        balance: str = "100.0",
        open_orders: dict | None = None,
        closed_orders: dict | None = None,
        ask_price: str = "100.0",
    ) -> None:
        self.balance = balance
        self.open_orders = open_orders or {}
        self.closed_orders = closed_orders or {}
        self.ask_price = ask_price
        self.closed_order_queries: list[dict] = []
        self.created_orders: list[dict] = []

    def get_asset_pairs(self) -> dict:
        return {
            "XETHZEUR": {
                "altname": "ETHEUR",
                "base": "XETH",
                "quote": "ZEUR",
                "pair_decimals": 2,
                "lot_decimals": 8,
                "ordermin": "0.005",
            }
        }

    def get_assets(self) -> dict:
        return {"ZEUR": {"decimals": 4}}

    def get_time(self) -> int:
        return 1620000000

    def get_trade_balance(self) -> dict:
        return {"eb": "100.0"}

    def get_balance(self) -> dict:
        return {"ZEUR": self.balance, "XETH": "0.0"}

    def get_open_orders(self) -> dict:
        return self.open_orders

    def get_closed_orders(self, query: dict) -> dict:
        self.closed_order_queries.append(query)
        return self.closed_orders

    def get_pair_ticker(self, pair_name: str) -> dict:
        return {pair_name: {"a": [self.ask_price, "1", "1"]}}

    def create_order(
        self,
        pair: str,
        type: str,
        order_type: str,
        pair_price: float,
        volume: float,
        o_flags: str,
    ) -> dict:
        self.created_orders.append(
            {
                "pair": pair,
                "type": type,
                "order_type": order_type,
                "pair_price": pair_price,
                "volume": volume,
                "o_flags": o_flags,
            }
        )
        return {
            "txid": ["OTEST-ORDER-TXID"],
            "descr": {"order": "buy 0.19948000 ETHEUR @ limit 100.0"},
        }


def scheduled_config(**overrides) -> dict:
    pair_config = {
        "pair": "XETHZEUR",
        "amount": 20.0,
        "schedule": {
            "enabled": True,
            "cron": "*/5 * * * *",
            "timezone": "UTC",
        },
        "min_order_interval_minutes": 30,
    }
    pair_config.update(overrides)
    return {"dca_pairs": [pair_config]}


def legacy_config(**overrides) -> dict:
    pair_config = {"pair": "XETHZEUR", "amount": 20.0, "delay": 1}
    pair_config.update(overrides)
    return {"dca_pairs": [pair_config]}


def pair_order(pair: str = "ETHEUR", amount: float = 20.0) -> dict:
    return {
        "order-id": {
            "descr": {"pair": pair, "price": "100.0"},
            "vol": str(amount / 100.0),
        }
    }


@freeze_time("2021-05-03 00:00:00")
def test_run_result_returns_completed_skipped_and_failed_shapes(tmp_path):
    completed = run_pair(
        legacy_config(orders_filepath=str(tmp_path / "completed.csv")),
        "XETHZEUR",
        FakeKrakenApi(),
    )
    skipped = run_pair(
        legacy_config(
            max_price=90.0,
            orders_filepath=str(tmp_path / "skipped.csv"),
        ),
        "XETHZEUR",
        FakeKrakenApi(),
    )
    failed = run_pair(legacy_config(), "XXBTZEUR", FakeKrakenApi())

    assert isinstance(completed, RunResult)
    assert completed.pair == "XETHZEUR"
    assert completed.status == "completed"
    assert completed.reason is None
    assert completed.started_at == datetime(2021, 5, 3, 0, 0, 0)
    assert completed.finished_at == datetime(2021, 5, 3, 0, 0, 0)
    assert completed.order_txid == "OTEST-ORDER-TXID"
    assert completed.message

    assert skipped.status == "skipped"
    assert skipped.reason == "max_price_exceeded"
    assert skipped.order_txid is None
    assert skipped.message

    assert failed.status == "failed"
    assert failed.reason == "pair_not_found"
    assert failed.order_txid is None
    assert failed.message


@freeze_time("2021-05-03 00:00:00")
def test_manual_and_scheduled_runs_use_same_open_order_duplicate_guard():
    manual_ka = FakeKrakenApi(open_orders=pair_order())
    scheduled_ka = FakeKrakenApi(open_orders=pair_order())

    manual = run_pair(legacy_config(), "XETHZEUR", manual_ka)
    scheduled = run_pair(scheduled_config(), "XETHZEUR", scheduled_ka)

    assert manual.status == "skipped"
    assert manual.reason == "duplicate_order"
    assert manual_ka.created_orders == []
    assert scheduled.status == "skipped"
    assert scheduled.reason == "duplicate_order"
    assert scheduled_ka.created_orders == []


def test_run_pair_uses_default_min_order_interval_for_scheduled_pair(
    monkeypatch,
):
    captured_kwargs = {}

    class FakeDCA:
        def __init__(self, *args, **kwargs):
            captured_kwargs.update(kwargs)

        def handle_dca_logic(self):
            return type(
                "Outcome",
                (),
                {
                    "status": "skipped",
                    "reason": "duplicate_order",
                    "order_txid": None,
                    "message": "duplicate",
                },
            )()

    monkeypatch.setattr("krakendca.runner.DCA", FakeDCA)

    config = scheduled_config()
    del config["dca_pairs"][0]["min_order_interval_minutes"]

    result = run_pair(
        config,
        "XETHZEUR",
        FakeKrakenApi(open_orders=pair_order()),
    )

    assert result.status == "skipped"
    assert captured_kwargs["min_order_interval_minutes"] == 30


@freeze_time("2021-05-03 00:00:00")
def test_insufficient_funds_returns_failed_result():
    result = run_pair(
        legacy_config(),
        "XETHZEUR",
        FakeKrakenApi(balance="1.0"),
    )

    assert result.status == "failed"
    assert result.reason == "insufficient_funds"
    assert result.order_txid is None
    assert "Insufficient funds" in result.message


@freeze_time("2021-05-03 00:00:00")
def test_max_price_guard_returns_skipped_result():
    result = run_pair(
        legacy_config(max_price=90.0),
        "XETHZEUR",
        FakeKrakenApi(ask_price="100.0"),
    )

    assert result.status == "skipped"
    assert result.reason == "max_price_exceeded"
    assert result.order_txid is None


@freeze_time("2021-05-03 00:00:00")
def test_scheduled_run_logs_unwritable_order_history_failure(
    tmp_path,
    logging_capture,
):
    orders_path = tmp_path / "orders.csv"
    orders_path.mkdir()

    result = run_pair(
        scheduled_config(orders_filepath=str(orders_path)),
        "XETHZEUR",
        FakeKrakenApi(),
    )

    captured = logging_capture.read()
    assert result.status == "failed"
    assert result.reason == "history_unwritable"
    assert "Order history is not writable" in captured
    assert "No order submitted" in captured
