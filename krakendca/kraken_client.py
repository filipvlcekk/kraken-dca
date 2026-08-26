"""Small Kraken Spot REST client used by KrakenDCA."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import threading
import time
from typing import Any
from urllib.parse import urlencode

import httpx


class KrakenClient:
    """Minimal synchronous Kraken Spot REST API client."""

    _BASE_URL = "https://api.kraken.com"
    _USER_AGENT = "kraken-dca/1.0"

    api_public_key: str
    api_private_key: str

    def __init__(
        self,
        api_public_key: str = "",
        api_private_key: str = "",
        *,
        base_url: str = _BASE_URL,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_public_key = api_public_key
        self.api_private_key = api_private_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )
        self._nonce_lock = threading.Lock()
        self._last_nonce = 0

    def create_api_signature(
        self,
        uri_path: str,
        payload: dict[str, Any],
    ) -> str:
        """Create Kraken API-Sign header value for a private request."""
        encoded_payload = urlencode(payload).encode()
        nonce = str(payload["nonce"])
        message_hash = hashlib.sha256(nonce.encode() + encoded_payload)
        try:
            secret = base64.b64decode(self.api_private_key, validate=True)
        except binascii.Error as exc:
            raise ValueError("Incorrect Kraken API private key.") from exc
        signature = hmac.new(
            secret,
            uri_path.encode() + message_hash.digest(),
            hashlib.sha512,
        )
        return base64.b64encode(signature.digest()).decode()

    def get_assets(self) -> dict:
        """Get Kraken asset metadata."""
        return self._public("Assets")

    def get_asset_pairs(self) -> dict:
        """Get Kraken tradable asset pair metadata."""
        return self._public("AssetPairs")

    def get_time(self) -> int:
        """Get Kraken server unix time."""
        return self._public("Time").get("unixtime")

    def get_pair_ticker(self, pair: str) -> dict:
        """Get ticker information for a pair."""
        return self._public("Ticker", {"pair": pair})

    def get_balance(self) -> dict:
        """Get account balances."""
        return self._private("Balance")

    def get_trade_balance(self) -> dict:
        """Get account trade balance."""
        return self._private("TradeBalance")

    def get_open_orders(self) -> dict:
        """Get open orders keyed by txid."""
        return self._private("OpenOrders").get("open")

    def get_closed_orders(self, query: dict | None = None) -> dict:
        """Get closed orders keyed by txid."""
        return self._private("ClosedOrders", query).get("closed")

    def query_orders(self, txids: list[str]) -> dict:
        """Get orders keyed by txid."""
        return self._private("QueryOrders", {"txid": ",".join(txids)})

    def create_order(
        self,
        pair: str,
        type: str,
        order_type: str,
        price: float,
        volume: float,
        o_flags: str,
    ) -> dict:
        """Create an order through Kraken AddOrder."""
        return self._private(
            "AddOrder",
            {
                "pair": pair,
                "type": type,
                "ordertype": order_type,
                "price": price,
                "volume": volume,
                "oflags": o_flags,
            },
        )

    def _public(self, method: str, payload: dict | None = None) -> dict:
        path = f"/0/public/{method}"
        try:
            if payload:
                response = self._client.post(
                    path,
                    data=payload,
                    headers={
                        **self._headers(),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
            else:
                response = self._client.get(
                    path,
                    headers=self._headers(),
                )
        except httpx.RequestError as exc:
            raise ConnectionError(
                f"Kraken API request failed -> {exc}"
            ) from exc
        return self._result(response)

    def _private(self, method: str, payload: dict | None = None) -> dict:
        path = f"/0/private/{method}"
        signed_payload = dict(payload or {})
        signed_payload["nonce"] = self._nonce()
        signature = self.create_api_signature(path, signed_payload)
        try:
            response = self._client.post(
                path,
                data=signed_payload,
                headers={
                    **self._headers(),
                    "API-Key": self.api_public_key,
                    "API-Sign": signature,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except httpx.RequestError as exc:
            raise ConnectionError(
                f"Kraken API request failed -> {exc}"
            ) from exc
        return self._result(response)

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self._USER_AGENT}

    def _nonce(self) -> str:
        with self._nonce_lock:
            nonce = int(time.time() * 1000)
            if nonce <= self._last_nonce:
                nonce = self._last_nonce + 1
            self._last_nonce = nonce
            return str(nonce)

    @staticmethod
    def _result(response: httpx.Response) -> dict:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectionError(
                f"Kraken API HTTP error -> {exc.response.status_code}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(
                "Response received from API was wrongly formatted."
            ) from exc

        if not isinstance(payload, dict):
            raise ValueError(
                "Response received from API was wrongly formatted."
            )

        errors = payload.get("error") or []
        if errors:
            raise ValueError(f"Kraken API error -> {errors[0]}")

        if "result" not in payload:
            raise ValueError(
                "Response received from API was wrongly formatted."
            )

        return payload["result"]
