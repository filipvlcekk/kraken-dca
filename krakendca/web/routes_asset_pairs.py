"""Kraken asset pair search routes."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from krakenapi import KrakenApi

from krakendca.pair import Pair
from krakendca.web import auth
from krakendca.web.schemas import ApiException, ok

router = APIRouter(tags=["asset-pairs"])


@router.get("/api/asset-pairs")
async def search_asset_pairs(
    request: Request,
    q: str = Query(default=""),
):
    """Return compact Kraken asset pair suggestions for a search query."""
    auth.require_authenticated_session(request)
    try:
        asset_pairs = KrakenApi("", "").get_asset_pairs()
    except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
        raise ApiException(
            502,
            "kraken_error",
            str(exc),
        ) from exc

    return ok({"pairs": Pair.search_asset_pairs(asset_pairs, q)})
