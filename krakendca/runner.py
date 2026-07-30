"""Single-pair DCA runner with typed results."""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from krakendca.kraken_client import KrakenClient

from .dca import DCA
from .pair import Pair
from .utils import current_utc_datetime

logger = logging.getLogger(__name__)

_MIN_ORDER_INTERVAL_DEFAULT = 30


@dataclass
class RunResult:
    """Typed result returned by a single pair run."""

    pair: str
    status: str
    reason: Optional[str]
    started_at: datetime
    finished_at: Optional[datetime]
    order_txid: Optional[str]
    message: str


def run_pair(config: dict, pair_name: str, ka: KrakenClient) -> RunResult:
    """Run DCA logic for exactly one configured pair."""
    started_at = current_utc_datetime()
    pair_configs = _find_pair_configs(config, pair_name)
    if len(pair_configs) == 0:
        return _result(
            pair_name,
            "failed",
            "pair_not_found",
            started_at,
            None,
            f"Pair {pair_name} was not found in configuration.",
        )
    if len(pair_configs) > 1:
        return _result(
            pair_name,
            "failed",
            "duplicate_pair_config",
            started_at,
            None,
            f"Pair {pair_name} has multiple configuration entries.",
        )

    pair_config = pair_configs[0]

    try:
        asset_pairs = ka.get_asset_pairs()
        pair = Pair.get_pair_from_kraken(ka, asset_pairs, pair_name)
        dca = _build_dca(ka, config, pair_config, pair)
        outcome = dca.handle_dca_logic()
    except ValueError as exc:
        logger.warning("DCA run domain error for %s: %s", pair_name, exc)
        return _result(
            pair_name,
            "failed",
            "domain_error",
            started_at,
            None,
            str(exc),
        )
    except (ConnectionError, OSError, TimeoutError) as exc:
        logger.exception("DCA run failed for %s.", pair_name)
        return _result(
            pair_name,
            "failed",
            "kraken_error",
            started_at,
            None,
            str(exc),
        )

    return _result(
        pair_name,
        outcome.status,
        outcome.reason,
        started_at,
        outcome.order_txid,
        outcome.message,
    )


def _find_pair_configs(config: dict, pair_name: str) -> list[dict]:
    return [
        dca_pair
        for dca_pair in (config.get("dca_pairs") or [])
        if dca_pair.get("pair") == pair_name
    ]


def _build_dca(
    ka: KrakenClient,
    config: dict,
    pair_config: dict,
    pair: Pair,
) -> DCA:
    schedule = pair_config.get("schedule")
    cron_mode = schedule is not None
    delay = 1 if cron_mode else pair_config.get("delay")
    min_order_interval_minutes = None
    if cron_mode:
        min_order_interval_minutes = pair_config.get(
            "min_order_interval_minutes",
            _MIN_ORDER_INTERVAL_DEFAULT,
        )

    return DCA(
        ka,
        delay,
        pair,
        pair_config.get("amount"),
        limit_factor=pair_config.get("limit_factor", 1),
        max_price=pair_config.get("max_price", -1),
        ignore_differing_orders=pair_config.get(
            "ignore_differing_orders",
            False,
        ),
        orders_filepath=pair_config.get(
            "orders_filepath",
            config.get("orders_filepath", "orders.csv"),
        ),
        min_order_interval_minutes=min_order_interval_minutes,
    )


def _result(
    pair: str,
    status: str,
    reason: Optional[str],
    started_at: datetime,
    order_txid: Optional[str],
    message: str,
) -> RunResult:
    return RunResult(
        pair=pair,
        status=status,
        reason=reason,
        started_at=started_at,
        finished_at=current_utc_datetime(),
        order_txid=order_txid,
        message=message,
    )
